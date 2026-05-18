import os
import shutil
import subprocess
import sys
import time

# 自动获取当前电脑的用户名
CURRENT_USER = os.environ.get('USERNAME') or os.environ.get('USER') or 'unknown'

# 配置路径（自动适配当前用户）
CONFIG_PATH = rf"C:\Users\{CURRENT_USER}\.codex\config.toml"
BACKUP_PATH = rf"C:\Users\{CURRENT_USER}\.codex\config.toml.bak"
PROXY_SCRIPT = "run_proxy_debug3.py"

REQUIRED_GLOBALS = {
    "model_provider": '"deepseek"',
    "model": '"deepseek-v4-flash"',
}

PROVIDER_BLOCK = """
[model_providers.deepseek] 
name = "DeepSeek" 
base_url = "http://127.0.0.1:8765/v1" 
wire_api = "responses" 
requires_openai_auth = true 
"""

def backup_config():
    print(f"[*] 正在备份配置文件到 {BACKUP_PATH}...")
    shutil.copy2(CONFIG_PATH, BACKUP_PATH)

def restore_config():
    if os.path.exists(BACKUP_PATH):
        print(f"[*] 正在还原配置文件...")
        shutil.copy2(BACKUP_PATH, CONFIG_PATH)
        try:
            os.remove(BACKUP_PATH)
        except:
            pass
        print("[+] 配置文件已还原。")

def check_and_cleanup_previous_session():
    if os.path.exists(BACKUP_PATH):
        print("[!] 检测到上次代理异常关闭（可能直接点击了 X 按钮）")
        print("[*] 正在执行启动前自动清理，还原初始配置...")
        restore_config()

def inject_proxy_config():
    print(f"[*] 正在注入代理配置到 {CONFIG_PATH}...")
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    found_keys = set()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
            continue
            
        matched = False
        for key, value in REQUIRED_GLOBALS.items():
            if stripped.startswith(f"{key} =") or stripped.startswith(f"{key}="):
                new_lines.append(f"{key} = {value}\n")
                found_keys.add(key)
                matched = True
                break
        
        if matched:
            continue

        if stripped.startswith("[model_providers.deepseek]"):
            continue
        
        if "model_providers.deepseek" in stripped:
            continue
            
        new_lines.append(line)

    header = []
    for key, value in REQUIRED_GLOBALS.items():
        if key not in found_keys:
            header.append(f"{key} = {value}\n")
    
    if header:
        new_lines = header + ["\n"] + new_lines

    if not any("[model_providers.deepseek]" in line for line in new_lines):
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append("\n" + PROVIDER_BLOCK + "\n")

    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("[+] 代理配置注入成功（含全局变量强制注入）。")

def main():
    try:
        check_and_cleanup_previous_session()
        
        backup_config()
        inject_proxy_config()
        
        print("\n" + "="*40)
        print("   DeepSeek 代理服务器启动中...")
        print(f"   当前用户: {CURRENT_USER}")
        print("   (建议使用 Ctrl+C 正常关闭以立即还原配置)")
        print("   (点击 X 强制关闭将在下次启动时自动还原)")
        print("="*40 + "\n")
        
        process = subprocess.Popen([sys.executable, PROXY_SCRIPT])
        process.wait()
        
    except KeyboardInterrupt:
        print("\n[*] 检测到用户中断...")
    except Exception as e:
        print(f"[-] 发生错误: {e}")
    finally:
        restore_config()

if __name__ == "__main__":
    main()
