#!/usr/bin/env python3
"""
Ubuntu 视频预处理脚本
功能：
1. 从 /mnt/d/recap_recordings 读取数据
2. 将 video.mp4 转换为 192x192 分辨率
3. 复制 annotation.proto
4. 按 delta_force_data 结构保存

使用方法：
    python3 scripts/preprocess_data_ubuntu.py
"""

import os
import sys
import shutil
import logging
import subprocess
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 路径配置
SOURCE_DIR = "/mnt/d/recap_recordings"          # Windows 共享目录
OUTPUT_DIR = os.path.expanduser("~/open-p2p/delta_force_data")  # 输出目录

# 视频参数
FRAME_HEIGHT = 192
FRAME_WIDTH = 192
BATCH_SIZE = 100  # 每个 batch 文件夹中的数据数量


def check_ffmpeg():
    """检查 ffmpeg 是否安装"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info("✓ ffmpeg 已安装")
            return True
    except FileNotFoundError:
        pass
    
    logger.error("✗ ffmpeg 未安装")
    logger.info("请运行: sudo apt install ffmpeg")
    return False


def rescale_video(input_path: str, output_path: str) -> bool:
    """
    使用 ffmpeg 将视频转换为 192x192 分辨率
    
    Args:
        input_path: 输入视频路径
        output_path: 输出视频路径
    
    Returns:
        True if successful, False otherwise
    """
    # ffmpeg 命令
    # -vf scale: 缩放到目标分辨率
    # -c:v libx264: 使用 H.264 编码
    # -preset fast: 快速编码
    # -crf 23: 质量设置 (23 是较好的质量和大小平衡)
    # -pix_fmt yuv420p: 像素格式，兼容性好
    command = [
        "ffmpeg",
        "-i", input_path,
        "-vf", f"scale={FRAME_WIDTH}:{FRAME_HEIGHT}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-y",  # 覆盖已存在的文件
        output_path
    ]
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600  # 10分钟超时
        )
        
        if result.returncode != 0:
            logger.error(f"ffmpeg 错误: {result.stderr[-500:]}")  # 只显示最后500字符
            return False
        
        return True
        
    except subprocess.TimeoutExpired:
        logger.error(f"视频处理超时: {input_path}")
        return False
    except Exception as e:
        logger.error(f"处理失败: {e}")
        return False


def get_valid_data_dirs(src_dir: str) -> list:
    """
    获取所有有效的数据目录
    有效目录包含 annotation.proto 和 video.mp4
    """
    valid_dirs = []
    
    if not os.path.exists(src_dir):
        logger.error(f"源目录不存在: {src_dir}")
        return valid_dirs
    
    for item in os.listdir(src_dir):
        item_path = os.path.join(src_dir, item)
        
        # 跳过非目录项
        if not os.path.isdir(item_path):
            continue
        
        # 检查必需文件
        proto_path = os.path.join(item_path, 'annotation.proto')
        video_path = os.path.join(item_path, 'video.mp4')
        
        if os.path.exists(proto_path) and os.path.exists(video_path):
            valid_dirs.append(item_path)
        else:
            missing = []
            if not os.path.exists(proto_path):
                missing.append('annotation.proto')
            if not os.path.exists(video_path):
                missing.append('video.mp4')
            logger.warning(f"跳过 {item} - 缺少: {', '.join(missing)}")
    
    return valid_dirs


def process_data_dirs(data_dirs: list, output_dir: str) -> dict:
    """
    处理所有数据目录，转换为目标结构
    
    Args:
        data_dirs: 有效数据目录列表
        output_dir: 输出根目录
    
    Returns:
        处理统计 {"success": int, "failed": int}
    """
    os.makedirs(output_dir, exist_ok=True)
    
    stats = {"success": 0, "failed": 0}
    
    batch_idx = 0
    data_idx = 0
    
    total = len(data_dirs)
    logger.info(f"开始处理 {total} 个数据目录...")
    
    for src_dir_path in data_dirs:
        dir_name = os.path.basename(src_dir_path)
        
        # 创建批次目录 (每 BATCH_SIZE 个数据创建一个 batch)
        if data_idx % BATCH_SIZE == 0:
            batch_dir = os.path.join(output_dir, f"batch_{batch_idx:05d}")
            os.makedirs(batch_dir, exist_ok=True)
            batch_idx += 1
            logger.info(f"\n创建批次: batch_{batch_idx-1:05d}")
        
        # 创建数据目录
        data_dir = os.path.join(batch_dir, f"data_{data_idx:05d}")
        os.makedirs(data_dir, exist_ok=True)
        
        logger.info(f"  [{data_idx+1}/{total}] {dir_name}")
        
        # 复制 annotation.proto
        src_proto = os.path.join(src_dir_path, 'annotation.proto')
        dst_proto = os.path.join(data_dir, 'annotation.proto')
        try:
            shutil.copy2(src_proto, dst_proto)
        except Exception as e:
            logger.error(f"    复制 annotation.proto 失败: {e}")
            stats["failed"] += 1
            data_idx += 1
            continue
        
        # 转换视频
        src_video = os.path.join(src_dir_path, 'video.mp4')
        dst_video = os.path.join(data_dir, 'video.mp4')
        
        if rescale_video(src_video, dst_video):
            stats["success"] += 1
        else:
            stats["failed"] += 1
        
        data_idx += 1
    
    return stats


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("视频预处理脚本 - Ubuntu 版本")
    logger.info("=" * 60)
    
    # 检查 ffmpeg
    if not check_ffmpeg():
        sys.exit(1)
    
    # 检查源目录
    if not os.path.exists(SOURCE_DIR):
        logger.error(f"源目录不存在: {SOURCE_DIR}")
        logger.info("请确保 Windows 共享目录已挂载到 /mnt/d/")
        sys.exit(1)
    
    logger.info(f"源目录: {SOURCE_DIR}")
    logger.info(f"输出目录: {OUTPUT_DIR}")
    logger.info(f"目标分辨率: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    logger.info("")
    
    # 获取有效数据目录
    data_dirs = get_valid_data_dirs(SOURCE_DIR)
    
    if not data_dirs:
        logger.warning("没有找到有效的数据目录")
        sys.exit(0)
    
    logger.info(f"找到 {len(data_dirs)} 个有效数据目录")
    logger.info("")
    
    # 确认继续
    response = input(f"是否开始处理? (y/n): ").strip().lower()
    if response != 'y':
        logger.info("已取消")
        sys.exit(0)
    
    # 处理数据
    logger.info("")
    stats = process_data_dirs(data_dirs, OUTPUT_DIR)
    
    # 输出结果
    logger.info("")
    logger.info("=" * 60)
    logger.info("处理完成!")
    logger.info(f"成功: {stats['success']}")
    logger.info(f"失败: {stats['failed']}")
    logger.info(f"输出目录: {OUTPUT_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
