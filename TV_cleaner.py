import os
import re

# --- 配置区 ---
SCAN_DIR = "/volume1/NAS123/Media/json/box/TV"
MAX_FILE_SIZE = 300 * 1024  # 300KB 开头重切分标准


def convert_m3u_to_txt(file_path):
    """1. 智能将 m3u 转换为符合规范的 tvbox txt 格式"""
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    name_without_ext = os.path.splitext(base_name)[0]
    target_txt_path = os.path.join(dir_name, f"{name_without_ext}.txt")

    print(f"📦 [M3U转换] 正在解析: {base_name}")
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 分解行
        lines = content.splitlines()
        txt_channels = {}  # group -> [channels]

        current_group = "未分类"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#EXTINF"):
                # 提取 group-title
                group_match = re.search(r'group-title="([^"]+)"', line)
                if group_match:
                    current_group = group_match.group(1)
                else:
                    # 尝试兼容没有 group-title 但有逗号后名称的情况
                    current_group = "直播源"
                
                # 尝试提取频道名称
                name_split = line.split(",")
                channel_name = name_split[-1].strip() if len(name_split) > 1 else "未命名频道"
                txt_channels.setdefault(current_group, [])
                # 暂存名称，下一行读取 URL
                txt_channels[current_group].append({"name": channel_name, "url": ""})
            elif line.startswith("http") or line.startswith("rtsp") or line.startswith("p2p"):
                # 填充上一个被记录频道的 URL
                if current_group in txt_channels and txt_channels[current_group]:
                    if txt_channels[current_group][-1]["url"] == "":
                        txt_channels[current_group][-1]["url"] = line

        # 写入新的 TXT 文件
        with open(target_txt_path, "w", encoding="utf-8") as f:
            for group, channels in txt_channels.items():
                f.write(f"{group},#genre#\n")
                for ch in channels:
                    if ch["url"]:  # 确保有有效 URL
                        f.write(f"{ch['name']},{ch['url']}\n")
                f.write("\n")

        # 物理移除老旧 m3u
        os.remove(file_path)
        print(f"✅ [M3U转换成功] 已生成并替换为: {name_without_ext}.txt")
    except Exception as e:
        print(f"❌ [M3U转换失败] 处理 {base_name} 出错: {e}")


def merge_pre_split_files():
    """2. 碎片大复原：把之前分裂出来的 _1, _2 重新合并为完整大文件做比对"""
    print("🔄 [合璧阶段] 正在搜寻并临时复原被切碎的 txt 文件...")
    
    # 建立合并映射关系
    merge_groups = {}
    
    for dirpath, _, filenames in os.walk(SCAN_DIR):
        for fname in filenames:
            if fname.endswith(".txt"):
                # 匹配形如 xxx_1.txt, xxx_22.txt
                match = re.match(r"^(.+)_(\d+)\.txt$", fname)
                if match:
                    origin_base = match.group(1)
                    full_origin_path = os.path.join(dirpath, f"{origin_base}.txt")
                    part_path = os.path.join(dirpath, fname)
                    part_idx = int(match.group(2))
                    
                    merge_groups.setdefault(full_origin_path, [])
                    merge_groups[full_origin_path].append((part_idx, part_path))

    # 执行物理合并还原
    for origin_path, part_list in merge_groups.items():
        # 按照碎片序号升序排序，保证内容按原有顺序合并
        part_list.sort(key=lambda x: x[0])
        
        combined_content = []
        for _, part_path in part_list:
            try:
                with open(part_path, "r", encoding="utf-8", errors="ignore") as f:
                    combined_content.append(f.read())
                os.remove(part_path)  # 删掉碎片
            except Exception as e:
                print(f"⚠️ 读取碎片失败 {part_path}: {e}")
        
        # 将合并后的内容写入原始主干文件
        if combined_content:
            with open(origin_path, "w", encoding="utf-8") as f:
                f.write("\n".join(combined_content))
            print(f"合并复原: {os.path.basename(origin_path)} (共还原了 {len(part_list)} 个碎片)")


def clean_and_deduplicate_file_content(file_path):
    """3. 单文件行级精细化清洗与去重"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        cleaned_lines = []
        seen_lines = set()

        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue
            
            # 允许分类标记重复路过，后面重新生成
            if "#genre#" in line_strip:
                continue
                
            # 直播源标准格式判定 (包含逗号且后面有链接)
            if "," in line_strip and any(x in line_strip for x in ["http", "rtsp", "p2p", "mitv"]):
                if line_strip not in seen_lines:
                    seen_lines.add(line_strip)
                    cleaned_lines.append(line_strip + "\n")

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(cleaned_lines)
            
        return seen_lines  # 返回这个文件所拥有的所有纯净源集合
    except Exception as e:
        print(f"⚠️ 清洗单文件失败 {os.path.basename(file_path)}: {e}")
        return set()


def cross_file_deduplication():
    """4. 跨文件「大吞小」全局查重逻辑"""
    print("🕵️‍♂️ [全局对账] 正在开展跨文件重叠度深度审查 (大吞小)...")
    
    file_data = []
    
    # 收集当前全库的合并大文件数据
    for dirpath, _, filenames in os.walk(SCAN_DIR):
        for fname in filenames:
            if fname.endswith(".txt") and "tvbox_all_index" not in fname:
                fpath = os.path.join(dirpath, fname)
                # 清洗并获取源集合
                urls_set = clean_and_deduplicate_file_content(fpath)
                if urls_set:
                    file_data.append({
                        "path": fpath,
                        "name": fname,
                        "urls": urls_set,
                        "size": len(urls_set)
                    })

    # 按包含的播放源数量「从大到小」严格排序
    file_data.sort(key=lambda x: x["size"], reverse=True)
    
    deleted_files = set()

    # 双层循环比对
    for i in range(len(file_data)):
        large_file = file_data[i]
        if large_file["path"] in deleted_files:
            continue
            
        for j in range(i + 1, len(file_data)):
            small_file = file_data[j]
            if small_file["path"] in deleted_files:
                continue
                
            # 计算小文件在大文件中的重合量
            intersection = large_file["urls"].intersection(small_file["urls"])
            if not small_file["urls"]:
                continue
                
            overlap_ratio = len(intersection) / len(small_file["urls"])
            
            # 🌟 阈值设定：如果小文件有 80% 以上的内容被大文件涵盖，触发吞噬直接干掉小文件
            if overlap_ratio >= 0.80:
                print(f"🗑️ [大吞小消灭] '{large_file['name']}' 涵盖了 '{small_file['name']}' {round(overlap_ratio*100, 1)}% 的内容。优先删除小文件。")
                try:
                    os.remove(small_file["path"])
                    deleted_files.add(small_file["path"])
                except Exception as e:
                    print(f"⚠️ 物理删除失败 {small_file['name']}: {e}")

    print(f"✨ 全局查重完成，共清洗并剔除了 {len(deleted_files)} 个高度重复的套娃小文件。")


def final_split_and_fix():
    """5. 对查重后幸存的完整大文件，重新按 300KB 标准进行合规切割"""
    print("✂️ [二次重组] 重新将清洗后的幸存资产分割为 300KB 规格规范体...")
    
    for dirpath, _, filenames in os.walk(SCAN_DIR):
        for fname in filenames:
            if fname.endswith(".txt") and "tvbox_all_index" not in fname:
                file_path = os.path.join(dirpath, fname)
                file_size = os.path.getsize(file_path)
                name_without_ext, ext = os.path.splitext(fname)
                
                # 如果没超重，直接加头部
                if file_size <= MAX_FILE_SIZE:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    if lines and "#genre#" not in lines[0]:
                        lines.insert(0, f"{name_without_ext},#genre#\n")
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.writelines(lines)
                    continue
                
                # 超重文件切割
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    all_lines = f.readlines()
                
                part_num = 1
                current_lines = []
                current_size = 0
                
                for line in all_lines:
                    line_bytes = len(line.encode("utf-8"))
                    if current_size + line_bytes > (MAX_FILE_SIZE - 2000):
                        if current_lines:
                            new_fname = f"{name_without_ext}_{part_num}{ext}"
                            new_fpath = os.path.join(dirpath, new_fname)
                            current_lines.insert(0, f"{name_without_ext}_{part_num},#genre#\n")
                            with open(new_fpath, "w", encoding="utf-8") as f:
                                f.writelines(current_lines)
                            part_num += 1
                            current_lines = []
                            current_size = 0
                    
                    current_lines.append(line)
                    current_size += line_bytes
                
                if current_lines:
                    new_fname = f"{name_without_ext}_{part_num}{ext}"
                    new_fpath = os.path.join(dirpath, new_fname)
                    current_lines.insert(0, f"{name_without_ext}_{part_num},#genre#\n")
                    with open(new_fpath, "w", encoding="utf-8") as f:
                        f.writelines(current_lines)
                
                # 移除合并后的大文件
                os.remove(file_path)


if __name__ == "__main__":
    print("=" * 70)
    print("🛡️  TVBox 影视配置源全局全自动洗版去重引擎 启动...")
    print("=" * 70)

    # 阶段 1: 预先扫描处理全部的 .m3u 文件为标准的 .txt 格式
    for root, dirs, files in os.walk(SCAN_DIR):
        for file in files:
            if file.endswith(".m3u") or file.endswith(".m3u8"):
                convert_m3u_to_txt(os.path.join(root, file))

    # 阶段 2: 将之前分割的所有碎文件重新合并，恢复完整大文件做横向对账
    merge_pre_split_files()

    # 阶段 3 & 4: 跨文件进行“大吞小”全局高重合度判定去重
    cross_file_deduplication()

    # 阶段 5: 将清洗幸存的文件按 300KB 标准重新做切分封装
    final_split_and_fix()

    print("=" * 70)
    print("🎉 全库深度清洗、去重包含、格式转化并规范切片完成！")
    print("💡 提示：现在可以运行你的 `TV.py` 脚本来重新生成最新的主索引大表了。")
    print("=" * 70)