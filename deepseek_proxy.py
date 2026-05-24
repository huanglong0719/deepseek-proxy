#!/usr/bin/env python3
"""
DeepSeek API Protocol Converter with Streaming Support
"""

import http.server
import json
import os
import urllib.request
import urllib.error
import sys
import time
import uuid
import base64
import tempfile

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
BROWSER_PROXY_URL = "http://127.0.0.1:8766/v1/chat/completions"
PORT = 8765

DEFAULT_MODEL = "deepseek-v4-flash"

def convert_role(role):
    role_map = {
        'developer': 'system',
        'system': 'system',
        'user': 'user',
        'assistant': 'assistant',
        'tool': 'tool',
        'latest_reminder': 'user'
    }
    return role_map.get(role, 'user')

TEMP_DIR = os.path.join(tempfile.gettempdir(), "deepseek_proxy_files")
os.makedirs(TEMP_DIR, exist_ok=True)

def save_base64_to_temp_file(data_url):
    try:
        if not data_url or not data_url.startswith("data:"):
            return None
        header_part, b64_part = data_url.split(",", 1)
        mime_type = header_part.split(":")[1].split(";")[0] if ":" in header_part else "application/octet-stream"
        ext_map = {
            "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
            "image/webp": ".webp", "image/svg+xml": ".svg",
            "application/pdf": ".pdf", "text/plain": ".txt",
            "application/json": ".json", "text/csv": ".csv",
            "application/zip": ".zip", "audio/mpeg": ".mp3",
            "audio/wav": ".wav", "video/mp4": ".mp4"
        }
        ext = ext_map.get(mime_type, ".bin")
        file_id = uuid.uuid4().hex[:12]
        filename = f"file_{file_id}{ext}"
        filepath = os.path.join(TEMP_DIR, filename)
        raw_data = base64.b64decode(b64_part)
        with open(filepath, "wb") as f:
            f.write(raw_data)
        print(f"    [FILE_SAVED] {filepath} ({len(raw_data)} bytes, {mime_type})")
        return filepath
    except Exception as e:
        print(f"    [FILE_SAVE_ERROR] {e}")
        return None

def has_image_content(request_data):
    input_items = request_data.get('input', [])
    for item in reversed(input_items):
        if not isinstance(item, dict):
            continue
        item_type = item.get('type', 'message')
        role = item.get('role', '')
        if item_type in ('function_call', 'function_call_output'):
            continue
        if role != 'user':
            continue
        content = item.get('content', '')
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get('type') in ('input_image', 'image_url'):
                    return True
        elif isinstance(content, dict) and content.get('type') in ('input_image', 'image_url'):
            return True
        return False
    return False

def has_image_in_messages(messages):
    for msg in messages:
        content = msg.get('content', '')
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get('type') in ('input_image', 'image_url'):
                    return True
    return False

def build_image_chat_request(request_data):
    messages = []
    instructions = request_data.get('instructions', '')
    if instructions:
        messages.append({"role": "system", "content": instructions})

    input_items = request_data.get('input', [])

    last_user_idx = -1
    for i in range(len(input_items) - 1, -1, -1):
        item = input_items[i]
        if not isinstance(item, dict):
            continue
        if item.get('type', 'message') in ('function_call', 'function_call_output'):
            continue
        if item.get('role', '') == 'user':
            last_user_idx = i
            break

    for idx, item in enumerate(input_items):
        if not isinstance(item, dict):
            continue
        item_type = item.get('type', 'message')
        if item_type in ('function_call', 'function_call_output'):
            continue
        role = convert_role(item.get('role', 'user'))
        content = item.get('content', '')
        if not isinstance(content, list):
            continue
        parts = []
        is_last_user = (idx == last_user_idx)
        for c in content:
            if not isinstance(c, dict):
                continue
            ct = c.get('type', '')
            if ct in ('input_image', 'image_url'):
                if is_last_user:
                    image_url = c.get('image_url', '') or c.get('url', '')
                    if isinstance(image_url, dict):
                        image_url = image_url.get('url', '')
                    if image_url and isinstance(image_url, str):
                        parts.append({
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        })
            elif ct in ('input_text', 'output_text', 'text'):
                text_val = c.get('text', '')
                if text_val:
                    parts.append({"type": "text", "text": text_val})
        if parts:
            messages.append({"role": role, "content": parts})

    return {
        "model": "deepseek-v4-pro",
        "messages": messages
    }

def forward_image_to_browser(chat_request):
    data = json.dumps(chat_request).encode('utf-8')
    req = urllib.request.Request(BROWSER_PROXY_URL, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', 'Bearer sk-browser-proxy-key-2026')
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode('utf-8'))

def send_image_streaming_response(self, browser_resp, model):
    print(f"    [SSE_STREAM] starting SSE stream...")
    sys.stdout.flush()
    choices = browser_resp.get('choices', [])
    message = choices[0].get('message', {}) if choices else {}
    content = message.get('content', '')
    resp_id = f"resp_{uuid.uuid4().hex[:24]}"
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    evt_id = f"evt_{uuid.uuid4().hex[:24]}"

    self.send_response(200)
    self.send_header('Content-Type', 'text/event-stream')
    self.send_header('Cache-Control', 'no-cache')
    self.send_header('Connection', 'keep-alive')
    self.send_header('Access-Control-Allow-Origin', '*')
    self.end_headers()

    def send_event(event_type, data):
        event_data = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"event: {event_type}\ndata: {event_data}\n\n".encode('utf-8'))
        self.wfile.flush()

    send_event("response.created", {
        "type": "response.created",
        "response": {
            "id": resp_id,
            "object": "response",
            "created_at": int(time.time()),
            "model": model,
            "status": "in_progress",
            "output": []
        }
    })

    send_event("response.output_item.added", {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": []
        }
    })

    send_event("response.content_part.added", {
        "type": "response.content_part.added",
        "output_index": 0,
        "content_index": 0,
        "part": {"type": "output_text", "text": ""}
    })

    send_event("response.output_text.delta", {
        "type": "response.output_text.delta",
        "output_index": 0,
        "content_index": 0,
        "delta": content
    })

    send_event("response.output_text.done", {
        "type": "response.output_text.done",
        "output_index": 0,
        "content_index": 0,
        "text": content
    })

    send_event("response.content_part.done", {
        "type": "response.content_part.done",
        "output_index": 0,
        "content_index": 0,
        "part": {"type": "output_text", "text": content}
    })

    send_event("response.output_item.done", {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": content}]
        }
    })

    send_event("response.completed", {
        "type": "response.completed",
        "event_id": evt_id,
        "response": {
            "id": resp_id,
            "object": "response",
            "created_at": int(time.time()),
            "model": model,
            "status": "completed",
            "incomplete_details": None,
            "output": [{
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": content}]
            }],
            "usage": browser_resp.get('usage', {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0
            }),
            "metadata": {}
        }
    })

    time.sleep(0.3)
    self.close_connection = True
    print(f"    [SSE_STREAM] done, {len(content)} chars")

def convert_browser_response_to_codex(browser_resp, model):
    choices = browser_resp.get('choices', [])
    message = choices[0].get('message', {}) if choices else {}
    content = message.get('content', '')
    resp_id = f"resp_{uuid.uuid4().hex[:24]}"
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    return {
        "id": resp_id,
        "object": "response",
        "created_at": browser_resp.get('created', int(time.time())),
        "model": model or "deepseek-v4-pro",
        "output": [{
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": content}]
        }],
        "usage": browser_resp.get('usage', {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }),
        "status": "completed"
    }
def convert_content_for_deepseek(content):
    if content is None:
        return ""
    if isinstance(content, str):
        if content == "<image>" or content.startswith("<image name="):
            return "[用户发送了一张图片]"
        return content
    if isinstance(content, list):
        result = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type in ("input_text", "output_text", "text"):
                    text = item.get("text", "")
                    if text and text != "<image>" and not text.startswith("<image name="):
                        result.append({"type": "text", "text": text})
                elif item_type in ("input_image", "image_url"):
                    image_data = item.get("image_url", "")
                    if isinstance(image_data, dict):
                        image_data = image_data.get("url", "")
                    if image_data and isinstance(image_data, str) and image_data.startswith("data:"):
                        saved_path = save_base64_to_temp_file(image_data)
                        if saved_path:
                            result.append({"type": "text", "text": f"[用户发送了一个文件(已保存到本地): {saved_path}]"})
                        else:
                            result.append({"type": "text", "text": "[用户发送了一个文件，但保存失败]"})
                    elif image_data and isinstance(image_data, str) and (image_data.startswith("http://") or image_data.startswith("https://")):
                        result.append({"type": "text", "text": f"[用户发送了一个网络文件链接: {image_data}]"})
                    else:
                        result.append({"type": "text", "text": "[用户发送了一个文件]"})
                else:
                    text = item.get("text", "") or item.get("content", "")
                    if text and text != "<image>" and not text.startswith("<image name="):
                        result.append({"type": "text", "text": text})
            elif isinstance(item, str):
                if item != "<image>" and not item.startswith("<image name="):
                    result.append({"type": "text", "text": item})
        if not result:
            return ""
        if len(result) == 1 and result[0]["type"] == "text":
            return result[0]["text"]
        return result
    return str(content)

def extract_text_content(content):
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') in ('output_text', 'input_text'):
                    text_parts.append(item.get('text', ''))
                elif 'text' in item:
                    text_parts.append(item.get('text', ''))
            elif isinstance(item, str):
                text_parts.append(item)
        return '\n'.join(text_parts)
    return str(content)

def normalize_model(model):
    if not model or model.startswith('gpt'):
        return DEFAULT_MODEL
    return model

def normalize_reasoning_effort(effort):
    if not effort or effort == "none":
        return None
    if effort in ("minimal", "low", "medium"):
        return "high"
    if effort == "xhigh":
        return "max"
    return effort

class ProtocolHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    
    def log_message(self, format, *args):
        pass

    def send_json_response(self, data, status=200):
        response = json.dumps(data, ensure_ascii=False)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(response.encode('utf-8')))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))
        print(f"[{time.strftime('%H:%M:%S')}] Response: {status}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Content-Length', 0)
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self.send_json_response({"status": "ok"})
        elif self.path in ('/v1/models', '/models'):
            self.send_json_response({
                "object": "list",
                "data": [
                    {"id": "deepseek-v4-flash", "object": "model"},
                    {"id": "deepseek-v4-pro", "object": "model"}
                ]
            })
        else:
            self.send_json_response({"error": "Not found"}, 404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        print(f"[{time.strftime('%H:%M:%S')}] POST {self.path}")
        
        try:
            request_data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json_response({"error": "Invalid JSON"}, 400)
            return

        # DEBUG: 打印完整的 input 内容（用于排查图片问题）
        if 'input' in request_data:
            for idx, item in enumerate(request_data.get('input', [])):
                if isinstance(item, dict):
                    content = item.get('content', '')
                    if isinstance(content, list):
                        for cidx, c in enumerate(content):
                            if isinstance(c, dict) and c.get('type') not in ('input_text', 'output_text', 'text'):
                                print(f"    [DEBUG] input[{idx}].content[{cidx}] = {json.dumps(c, ensure_ascii=False)[:500]}")
                    elif isinstance(content, str) and ('image' in content.lower() or '<image>' in content):
                        print(f"    [DEBUG] input[{idx}] contains image placeholder: {content[:200]}")
            
            # 保存完整请求到文件（用于分析图片数据）
            try:
                with open(os.path.join(os.path.expanduser('~'), '.codex', 'proxy_debug_request.json'), 'w', encoding='utf-8') as f:
                    json.dump(request_data, f, ensure_ascii=False, indent=2)
                print(f"    [DEBUG] 完整请求已保存到 proxy_debug_request.json")
            except Exception as e:
                print(f"    [DEBUG] 保存请求失败: {e}")

        if self.path in ('/responses', '/v1/responses'):
            self.handle_responses_api(request_data)
        elif self.path in ('/v1/chat/completions', '/chat/completions'):
            self.handle_chat_completions(request_data)
        else:
            self.send_json_response({"error": f"Unknown: {self.path}"}, 404)

    def handle_responses_api(self, request_data):
        try:
            model = normalize_model(request_data.get('model', DEFAULT_MODEL))

            if has_image_content(request_data):
                print(f"    [IMAGE_DETECTED] routing to browser proxy at {BROWSER_PROXY_URL}")
                try:
                    chat_req = build_image_chat_request(request_data)
                    print(f"    [BROWSER_FWD] sending {len(str(chat_req))} byte request")
                    browser_resp = forward_image_to_browser(chat_req)
                    print(f"    [BROWSER_RESP] got {len(browser_resp.get('choices',[]) or [])} choices")
                    choices = browser_resp.get('choices', [])
                    message = choices[0].get('message', {}) if choices else {}
                    content = message.get('content', '')
                    thinking = message.get('reasoning_content', '')

                    resp_id = f"resp_{uuid.uuid4().hex[:24]}"
                    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Connection', 'keep-alive')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()

                    seq = [0]
                    def next_seq():
                        seq[0] += 1
                        return seq[0]

                    def sse(event_type, data):
                        data["sequence_number"] = next_seq()
                        d = json.dumps(data, ensure_ascii=False)
                        self.wfile.write(f"event: {event_type}\ndata: {d}\n\n".encode('utf-8'))
                        self.wfile.flush()

                    sse("response.created", {
                        "type": "response.created",
                        "id": resp_id,
                        "response_id": resp_id,
                        "object": "response",
                        "model": model,
                        "status": "in_progress",
                    })

                    sse("response.output_item.added", {
                        "type": "response.output_item.added",
                        "id": resp_id,
                        "response_id": resp_id,
                        "output_index": 0,
                        "item_id": msg_id,
                        "item": {"id": msg_id, "type": "message", "role": "assistant", "content": []},
                    })

                    has_thinking = thinking and thinking.strip()
                    has_text = content and content.strip()

                    if has_thinking:
                        sse("response.content_part.added", {
                            "type": "response.content_part.added",
                            "id": resp_id,
                            "response_id": resp_id,
                            "item_id": msg_id,
                            "output_index": 0,
                            "content_index": 0,
                            "part": {"type": "reasoning", "text": ""},
                        })

                        sse("response.reasoning.delta", {
                            "type": "response.reasoning.delta",
                            "id": resp_id,
                            "response_id": resp_id,
                            "delta": thinking,
                        })

                        sse("response.content_part.done", {
                            "type": "response.content_part.done",
                            "id": resp_id,
                            "response_id": resp_id,
                            "item_id": msg_id,
                            "output_index": 0,
                            "content_index": 0,
                            "part": {"type": "reasoning", "text": thinking},
                        })

                        text_content_index = 1
                    else:
                        text_content_index = 0

                    if has_text:
                        sse("response.content_part.added", {
                            "type": "response.content_part.added",
                            "id": resp_id,
                            "response_id": resp_id,
                            "item_id": msg_id,
                            "output_index": 0,
                            "content_index": text_content_index,
                            "part": {"type": "output_text", "text": ""},
                        })

                        chunk_size = 50
                        chars = list(content)
                        for i in range(0, len(chars), chunk_size):
                            chunk = ''.join(chars[i:i+chunk_size])
                            sse("response.output_text.delta", {
                                "type": "response.output_text.delta",
                                "id": resp_id,
                                "response_id": resp_id,
                                "item_id": msg_id,
                                "output_index": 0,
                                "content_index": text_content_index,
                                "delta": chunk,
                            })
                            if i + chunk_size < len(chars):
                                time.sleep(0.01)

                        sse("response.output_text.done", {
                            "type": "response.output_text.done",
                            "id": resp_id,
                            "response_id": resp_id,
                            "item_id": msg_id,
                            "output_index": 0,
                            "content_index": text_content_index,
                            "text": content,
                        })

                        sse("response.content_part.done", {
                            "type": "response.content_part.done",
                            "id": resp_id,
                            "response_id": resp_id,
                            "item_id": msg_id,
                            "output_index": 0,
                            "content_index": text_content_index,
                            "part": {"type": "output_text", "text": content},
                        })

                    output_content = []
                    if has_thinking:
                        output_content.append({"type": "reasoning", "text": thinking})
                    if has_text:
                        output_content.append({"type": "output_text", "text": content})

                    sse("response.output_item.done", {
                        "type": "response.output_item.done",
                        "id": resp_id,
                        "response_id": resp_id,
                        "output_index": 0,
                        "item_id": msg_id,
                        "item": {"id": msg_id, "type": "message", "role": "assistant", "status": "completed", "content": output_content},
                    })

                    response_obj = {
                        "id": resp_id,
                        "object": "response",
                        "created_at": int(time.time()),
                        "model": model,
                        "status": "completed",
                        "incomplete_details": None,
                        "output": [{"id": msg_id, "type": "message", "role": "assistant", "status": "completed", "content": output_content}],
                        "usage": browser_resp.get('usage', {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}),
                        "metadata": {},
                    }
                    sse("response.completed", {
                        "type": "response.completed",
                        "response_id": resp_id,
                        "response": response_obj,
                    })

                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    self.close_connection = True
                    print(f"    [SSE_STREAM] done, content={len(content)}chars, thinking={len(thinking)}chars")
                    return
                except Exception as e:
                    print(f"    [BROWSER_ERR] {e}")
                    self.send_json_response(
                        {"error": f"Image recognition failed: {str(e)}"}, 502)
                    return

            stream = request_data.get('stream', True)
            tools = request_data.get('tools', [])
            tool_choice = request_data.get('tool_choice', 'auto')
            reasoning = request_data.get('reasoning', {})
            effort = normalize_reasoning_effort(
                reasoning.get('effort') if isinstance(reasoning, dict) else None
            )
            
            messages = []
            instructions = request_data.get('instructions', '')
            if instructions:
                messages.append({"role": "system", "content": instructions})
            
            for item in request_data.get('input', []):
                if not isinstance(item, dict):
                    continue
                role = convert_role(item.get('role', 'user'))
                item_type = item.get('type', 'message')
                
                if item_type == 'function_call':
                    tool_call_msg = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": item.get('call_id', f"call_{uuid.uuid4().hex[:8]}"),
                            "type": "function",
                            "function": {
                                "name": item.get('name', ''),
                                "arguments": item.get('arguments', '{}')
                            }
                        }]
                    }
                    messages.append(tool_call_msg)
                elif item_type == 'function_call_output':
                    call_id = item.get('call_id', '')
                    raw_output = item.get('output', '')
                    print(f"    [DEBUG_FUNC_OUTPUT] call_id={call_id} output_type={type(raw_output).__name__} output_len={len(raw_output) if raw_output else 0}")
                    if isinstance(raw_output, dict):
                        print(f"    [DEBUG_FUNC_OUTPUT] output_keys={list(raw_output.keys())}")
                        for k, v in raw_output.items():
                            vpreview = str(v)[:200] if v else '(None)'
                            print(f"    [DEBUG_FUNC_OUTPUT]   {k} type={type(v).__name__} preview={vpreview}")
                    elif isinstance(raw_output, list):
                        print(f"    [DEBUG_FUNC_OUTPUT] output_list_len={len(raw_output)}")
                        for idx, vi in enumerate(raw_output[:3]):
                            print(f"    [DEBUG_FUNC_OUTPUT]   [{idx}] type={type(vi).__name__} preview={str(vi)[:200]}")
                    elif isinstance(raw_output, str):
                        print(f"    [DEBUG_FUNC_OUTPUT] output_str_preview={raw_output[:300]}")
                    else:
                        print(f"    [DEBUG_FUNC_OUTPUT] raw_output_value={raw_output}")
                    content = extract_text_content(raw_output)
                    is_image_output = False
                    if not content and raw_output:
                        if isinstance(raw_output, list):
                            for item in raw_output:
                                if isinstance(item, dict) and item.get('type') in ('input_image', 'image_url'):
                                    is_image_output = True
                                    break
                        content = convert_content_for_deepseek(raw_output)
                        if content and is_image_output:
                            content = '[IMAGE_VIEW_RESULT] ' + content + ' -- 这是你请求查看的图片，请基于图片内容回答用户问题。'
                            print(f"    [DEBUG_FUNC_OUTPUT] image output converted, result={content[:200]}")
                        elif content:
                            print(f"    [DEBUG_FUNC_OUTPUT] fallback to convert_content_for_deepseek, result={str(content)[:150]}")
                    if not call_id:
                        print(f"    WARNING: function_call_output missing call_id, output={content[:50]}")
                    tool_result_msg = {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": content
                    }
                    messages.append(tool_result_msg)
                else:
                    content = convert_content_for_deepseek(item.get('content', ''))
                    if content or isinstance(content, list):
                        messages.append({"role": role, "content": content})

            if not messages:
                messages = [{"role": "user", "content": "Hello"}]

            merged = []
            for m in messages:
                if m.get('role') == 'assistant' and merged and merged[-1].get('role') == 'assistant':
                    last = merged[-1]
                    content = m.get('content')
                    if content:
                        existing = last.get('content', '')
                        if existing and isinstance(existing, str):
                            last['content'] = existing + '\n' + content
                        elif not existing:
                            last['content'] = content
                    tc = m.get('tool_calls')
                    if tc:
                        last.setdefault('tool_calls', []).extend(tc)
                else:
                    merged.append(m)
            messages = merged

            tool_ids = set()
            result_ids = set()
            for i, m in enumerate(messages):
                role = m.get('role', '?')
                if role == 'assistant' and m.get('tool_calls'):
                    for tc in m['tool_calls']:
                        tid = tc.get('id', '')
                        tname = tc.get('function', {}).get('name', '')
                        tool_ids.add(tid)
                        print(f"    [{i}] assistant tool_call id={tid} name={tname}")
                elif role == 'tool':
                    rid = m.get('tool_call_id', '')
                    rcontent = str(m.get('content', ''))[:60]
                    result_ids.add(rid)
                    print(f"    [{i}] tool result id={rid} content={rcontent}")
                else:
                    print(f"    [{i}] {role} content={str(m.get('content',''))[:80]}")
            if tool_ids and tool_ids != result_ids:
                print(f"    MISMATCH! tool_call_ids={tool_ids}, tool_result_ids={result_ids}")
            elif tool_ids:
                print(f"    Tool call/response IDs match: {tool_ids}")

            chat_request = {
                "model": model,
                "messages": messages,
                "stream": stream
            }

            if tools:
                chat_request["thinking"] = {"type": "disabled"}
            elif effort:
                chat_request["thinking"] = {"type": "enabled"}
                chat_request["reasoning_effort"] = effort

            if tools:
                # DeepSeek tools need specific format, simplify them
                ds_tools = []
                skipped_types = set()
                for t in tools:
                    if isinstance(t, dict) and t.get('type') == 'function':
                        ds_tools.append({
                            "type": "function",
                            "function": {
                                "name": t.get('name', t.get('function', {}).get('name', '')),
                                "description": t.get('description', t.get('function', {}).get('description', '')),
                                "parameters": t.get('parameters', t.get('function', {}).get('parameters', {"type": "object", "properties": {}}))
                            }
                        })
                    elif isinstance(t, dict):
                        skipped_types.add(t.get('type', 'unknown'))
                if skipped_types:
                    print(f"    Skipped non-function tools (types: {skipped_types})")
                if ds_tools:
                    chat_request['tools'] = ds_tools
                    if tool_choice and tool_choice != 'auto':
                        chat_request['tool_choice'] = tool_choice
                    print(f"    Tool names: {[t.get('function',{}).get('name','') for t in ds_tools]}")

            if 'max_output_tokens' in request_data:
                chat_request['max_tokens'] = request_data['max_output_tokens']
            if 'temperature' in request_data:
                chat_request['temperature'] = request_data['temperature']

            print(f"    Model: {model}, Stream: {stream}, Msgs: {len(messages)}, Tools: {len(tools)}")

            if stream:
                self.handle_streaming_response(chat_request, model)
            else:
                response = self.call_deepseek(chat_request)
                converted = self.convert_response(response, model)
                self.send_json_response(converted)

        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()
            try:
                self.send_json_response({"error": {"message": str(e)}}, 500)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    def handle_streaming_response(self, chat_request, model):
        url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        }
        
        response_id = f"resp_{uuid.uuid4().hex[:24]}"
        msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        def send_event(event_type, data):
            try:
                event_data = json.dumps(data, ensure_ascii=False)
                self.wfile.write(f"event: {event_type}\ndata: {event_data}\n\n".encode('utf-8'))
                self.wfile.flush()
            except Exception as e:
                print(f"    Send error: {e}")
                raise
        
        send_event("response.created", {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": int(time.time()),
                "model": model,
                "status": "in_progress",
                "output": []
            }
        })
        
        data = json.dumps(chat_request).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        
        full_content = ""
        full_tool_calls = []
        current_tool_index = -1
        input_tokens = 0
        output_tokens = 0
        
        next_output_index = 0
        message_output_index = -1
        message_started = False
        tool_output_indices = {}
        tool_call_ids = {}
        
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_str = line[6:]
                        if data_str == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get('choices', [])
                            if choices:
                                delta = choices[0].get('delta', {})
                                
                                content = delta.get('content', '')
                                if content:
                                    if not message_started:
                                        message_output_index = next_output_index
                                        next_output_index += 1
                                        message_started = True
                                        send_event("response.output_item.added", {
                                            "type": "response.output_item.added",
                                            "output_index": message_output_index,
                                            "item": {
                                                "id": msg_id,
                                                "type": "message",
                                                "role": "assistant",
                                                "content": []
                                            }
                                        })
                                        send_event("response.content_part.added", {
                                            "type": "response.content_part.added",
                                            "output_index": message_output_index,
                                            "content_index": 0,
                                            "part": {"type": "output_text", "text": ""}
                                        })
                                    
                                    full_content += content
                                    send_event("response.output_text.delta", {
                                        "type": "response.output_text.delta",
                                        "output_index": message_output_index,
                                        "content_index": 0,
                                        "delta": content
                                    })
                                
                                tool_calls_delta = delta.get('tool_calls', [])
                                if tool_calls_delta:
                                    for tc_delta in tool_calls_delta:
                                        tc_idx = tc_delta.get('index', 0)
                                        
                                        if tc_idx not in tool_output_indices:
                                            call_id = tc_delta.get('id', f"call_{uuid.uuid4().hex[:8]}")
                                            fc_id = f"fc_{uuid.uuid4().hex[:8]}"
                                            tool_output_indices[tc_idx] = next_output_index
                                            tool_call_ids[tc_idx] = call_id
                                            tc_output_index = next_output_index
                                            next_output_index += 1
                                            current_tool_index = tc_idx
                                            
                                            current_tool_call = {
                                                "id": fc_id,
                                                "call_id": call_id,
                                                "name": "",
                                                "arguments": ""
                                            }
                                            full_tool_calls.append(current_tool_call)
                                            
                                            send_event("response.output_item.added", {
                                                "type": "response.output_item.added",
                                                "output_index": tc_output_index,
                                                "item": {
                                                    "type": "function_call",
                                                    "id": fc_id,
                                                    "call_id": call_id,
                                                    "name": tc_delta.get('function', {}).get('name', '')
                                                }
                                            })
                                        
                                        func = tc_delta.get('function', {})
                                        tc = None
                                        cid = tool_call_ids.get(tc_idx, '')
                                        for ftc in full_tool_calls:
                                            if ftc['call_id'] == cid:
                                                tc = ftc
                                                break
                                        
                                        if 'name' in func and tc:
                                            tc['name'] = func['name']
                                        if 'arguments' in func and tc:
                                            tc['arguments'] += func.get('arguments', '')
                                            tc_output_index = tool_output_indices.get(tc_idx, 0)
                                            send_event("response.function_call_arguments.delta", {
                                                "type": "response.function_call_arguments.delta",
                                                "output_index": tc_output_index,
                                                "delta": func.get('arguments', '')
                                            })
                            
                            usage = chunk.get('usage', {})
                            if usage:
                                input_tokens = usage.get('prompt_tokens', 0)
                                output_tokens = usage.get('completion_tokens', 0)
                        except json.JSONDecodeError:
                            pass
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else 'No body'
            print(f"    HTTP Error {e.code}: {error_body[:500]}")
        except Exception as e:
            print(f"    Stream error: {e}")
        
        try:
            if message_started and full_content:
                send_event("response.output_text.done", {
                    "type": "response.output_text.done",
                    "output_index": message_output_index,
                    "content_index": 0,
                    "text": full_content
                })
                send_event("response.content_part.done", {
                    "type": "response.content_part.done",
                    "output_index": message_output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": full_content}
                })
                send_event("response.output_item.done", {
                    "type": "response.output_item.done",
                    "output_index": message_output_index,
                    "item": {
                        "id": msg_id,
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": full_content}]
                    }
                })
            
            for i, tc in enumerate(full_tool_calls):
                tc_idx = None
                for idx, cid in tool_call_ids.items():
                    if cid == tc['call_id']:
                        tc_idx = idx
                        break
                tc_output_index = tool_output_indices.get(tc_idx, i) if tc_idx is not None else i
                
                send_event("response.function_call_arguments.done", {
                    "type": "response.function_call_arguments.done",
                    "output_index": tc_output_index,
                    "arguments": tc['arguments']
                })
                send_event("response.output_item.done", {
                    "type": "response.output_item.done",
                    "output_index": tc_output_index,
                    "item": {
                        "type": "function_call",
                        "id": tc['id'],
                        "call_id": tc['call_id'],
                        "name": tc['name'],
                        "arguments": tc['arguments'],
                        "status": "completed"
                    }
                })
            
            output = []
            if message_started and full_content:
                output.append({
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": full_content}]
                })
            for tc in full_tool_calls:
                output.append({
                    "type": "function_call",
                    "id": tc['id'],
                    "call_id": tc['call_id'],
                    "name": tc['name'],
                    "arguments": tc['arguments'],
                    "status": "completed"
                })
            
            if not output:
                output.append({
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": ""}]
                })
            
            send_event("response.completed", {
                "type": "response.completed",
                "event_id": f"evt_{uuid.uuid4().hex[:24]}",
                "response": {
                    "id": response_id,
                    "object": "response",
                    "created_at": int(time.time()),
                    "model": model,
                    "status": "completed",
                    "incomplete_details": None,
                    "output": output,
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens
                    },
                    "metadata": {}
                }
            })
            
            time.sleep(0.3)
            self.close_connection = True
            print(f"    Stream done: {len(full_content)} chars, {len(full_tool_calls)} tool calls")
        except Exception as e:
            print(f"    Final send error: {e}")

    def handle_chat_completions(self, request_data):
        try:
            if has_image_in_messages(request_data.get('messages', [])):
                print(f"    [IMAGE_DETECTED_CHAT] routing to browser proxy")
                try:
                    browser_resp = forward_image_to_browser(request_data)
                    converted = convert_browser_response_to_codex(browser_resp, request_data.get('model', ''))
                    self.send_json_response(converted)
                    return
                except Exception as e:
                    print(f"    [BROWSER_CHAT_ERR] {e}")
                    self.send_json_response(
                        {"error": f"Image recognition failed: {str(e)}"}, 502)
                    return
            request_data['model'] = normalize_model(request_data.get('model', DEFAULT_MODEL))
            for msg in request_data.get('messages', []):
                msg['role'] = convert_role(msg.get('role', 'user'))
                msg['content'] = convert_content_for_deepseek(msg.get('content', ''))
            response = self.call_deepseek(request_data)
            self.send_json_response(response)
        except Exception as e:
            self.send_json_response({"error": {"message": str(e)}}, 500)

    def call_deepseek(self, chat_request):
        url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        }
        data = json.dumps(chat_request).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))

    def convert_response(self, chat_response, model):
        choices = chat_response.get('choices', [])
        message = choices[0].get('message', {}) if choices else {}
        content = message.get('content', '')
        
        output = []
        if content:
            output.append({
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": content}]
            })
        
        tool_calls = message.get('tool_calls', [])
        for tc in tool_calls:
            func = tc.get('function', {})
            args_str = func.get('arguments', '{}')
            output.append({
                "type": "function_call",
                "id": f"fc_{uuid.uuid4().hex[:8]}",
                "call_id": tc.get('id', ''),
                "name": func.get('name', ''),
                "arguments": args_str,
                "status": "completed"
            })
        
        if not output:
            output.append({
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": ""}]
            })
        
        return {
            "id": chat_response.get('id', f"resp_{uuid.uuid4().hex[:24]}"),
            "object": "response",
            "created_at": chat_response.get('created', int(time.time())),
            "model": model,
            "output": output,
            "usage": {
                "input_tokens": chat_response.get('usage', {}).get('prompt_tokens', 0),
                "output_tokens": chat_response.get('usage', {}).get('completion_tokens', 0),
                "total_tokens": chat_response.get('usage', {}).get('total_tokens', 0)
            },
            "status": "completed"
        }

def run_server():
    if not DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY is not set.")
        sys.exit(1)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), ProtocolHandler)
    print(f"\n{'='*60}")
    print(f"DeepSeek Protocol Converter (Streaming) - RUNNING")
    print(f"{'='*60}")
    print(f"Port: {PORT}")
    print(f"{'='*60}\n")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == '__main__':
    run_server()
