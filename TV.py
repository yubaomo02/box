import os

# --- 配置区 ---
SCAN_DIR = "/volume1/NAS123/Media/json/box/TV"
BASE_URL = "http://192.168.0.109:5555/box/TV"
OUTPUT_FILE = "/volume1/NAS123/Media/json/box/TV/tvbox_all_index.txt"

# 限制单个文件最大大小（300KB = 300 * 1024 字节）
MAX_FILE_SIZE = 300 * 1024


def split_and_fix_file(file_path):
    """🌟 核心增强：检查文件大小，大于 300KB 则按行拆分，并对所有新文件规范化开头"""
    # 如果文件本身不存在，直接跳过
    if not os.path.exists(file_path):
        return []

    file_size = os.path.getsize(file_path)
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    name_without_ext, ext = os.path.splitext(base_name)

    # 1. 如果文件小于或等于 300KB，直接进行原本的单文件格式自检
    if file_size <= MAX_FILE_SIZE:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            # 检查第一行是否含有 #genre#
            has_genre = any("#genre#" in line for line in lines[:1])
            if not has_genre and lines:
                print(f"🔧 [格式修复] 小文件 '{base_name}' 缺失开头，正在自动补回...")
                required_marker = f"{name_without_ext},#genre#\n"
                lines.insert(0, required_marker)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            return [base_name]
        except Exception as e:
            print(f"❌ [自检失败] 处理小文件 {base_name} 失败: {e}")
            return [base_name]

    # 2. 如果文件大于 300KB，开启大文件智能分裂逻辑
    print(f"✂️ [检测到超大文件] '{base_name}' ({round(file_size/1024, 1)}KB) 正在分裂...")
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
    except Exception as e:
        print(f"❌ [读取失败] 无法读取大文件 {base_name}: {e}")
        return [base_name]

    generated_files = []
    part_num = 1
    current_lines = []
    current_size = 0

    for line in all_lines:
        # 如果这一行本来就是分类标记，且不是第一部分，我们直接过滤掉，后面会统一重新生成
        if "#genre#" in line:
            continue

        line_bytes = len(line.encode("utf-8"))
        
        # 如果当前累积的行大小加上这一行，即将超过 300KB 阈值，则立即打包写入当前部分
        if current_size + line_bytes > (MAX_FILE_SIZE - 2000):  # 预留 2KB 空间给开头标记
            if current_lines:
                new_fname = f"{name_without_ext}_{part_num}{ext}"
                new_fpath = os.path.join(dir_name, new_fname)
                
                # 强行给每一部分补上它自己专属的独立名字开头
                part_marker = f"{name_without_ext}_{part_num},#genre#\n"
                current_lines.insert(0, part_marker)
                
                with open(new_fpath, "w", encoding="utf-8") as f:
                    f.writelines(current_lines)
                
                generated_files.append(new_fname)
                part_num += 1
                current_lines = []
                current_size = 0

        current_lines.append(line)
        current_size += line_bytes

    # 将剩余没写完的最后一部分尾数打包写入
    if current_lines:
        new_fname = f"{name_without_ext}_{part_num}{ext}"
        new_fpath = os.path.join(dir_name, new_fname)
        part_marker = f"{name_without_ext}_{part_num},#genre#\n"
        current_lines.insert(0, part_marker)
        
        with open(new_fpath, "w", encoding="utf-8") as f:
            f.writelines(current_lines)
        generated_files.append(new_fname)

    # 🌟 关键：分裂成功后，为了防止混乱，把原本的大体积源文件安全物理删除
    try:
        os.remove(file_path)
        print(f"🗑️ [清理完成] 已成功将 '{base_name}' 物理拆分为 {len(generated_files)} 个新文件，旧文件已删除。")
    except Exception as e:
        print(f"⚠️ [清理失败] 拆分成功但无法删除旧大文件: {e}")

    return generated_files


def generate_index():
    print("=" * 70)
    print(f"🚀 开始精准路径扫描 + 300KB大文件分裂修复机制...")
    print("=" * 70)

    if not os.path.exists(SCAN_DIR):
        print(f"❌ 错误：找不到指定的扫描目录 {SCAN_DIR}")
        return

    index_lines = []
    file_count = 0

    # 深度遍历
    for dirpath, dirnames, filenames in os.walk(SCAN_DIR):
        for fname in filenames:
            # 只处理 .txt 文件，且排除总索引文件自身和中途生成的新碎文件
            if fname.endswith(".txt") and fname != os.path.basename(OUTPUT_FILE):
                
                full_path = os.path.join(dirpath, fname)
                
                # 🌟 调用自检、分裂与开头修复函数。它会返回最终留在硬盘上的文件名列表
                active_files = split_and_fix_file(full_path)

                # 遍历处理完后真正留在硬盘上的文件，录入索引大表
                for active_fname in active_files:
                    rel_dir = os.path.relpath(dirpath, SCAN_DIR)
                    
                    if rel_dir == ".":
                        title_prefix = "未分类"
                        url_path = active_fname
                    else:
                        title_prefix = rel_dir.replace("/", "_").replace("\\", "_")
                        url_path = f"{rel_dir}/{active_fname}".replace("\\", "/")

                    # 生成索引标题
                    name_without_ext = os.path.splitext(active_fname)[0]
                    title_line = f"#{title_prefix}_{name_without_ext}"

                    # 生成对应的网络真实 URL 链接
                    url_line = f"{BASE_URL}/{url_path}"

                    index_lines.append(title_line)
                    index_lines.append(url_line)
                    file_count += 1

    # 写入最终的汇总文本文件
    if index_lines:
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(index_lines) + "\n")
            print("=" * 70)
            print(f"✨ 深度索引大表生成成功！当前全库共计 {file_count} 个合规配置文件。")
            print(f"📄 结果已安全写入: {OUTPUT_FILE}")
            print("=" * 70)
        except Exception as e:
            print(f"❌ 写入总索引文件失败，原因: {e}")
    else:
        print("⚠️ 未在该目录下找到任何有效的 .txt 配置文件！")


if __name__ == "__main__":
    generate_index()