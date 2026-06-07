#!/usr/bin/env python3
"""
Ubuntu 视频预处理脚本
功能：
1. 从 /mnt/d/recap_recordings 读取数据
2. 将 video.mp4 转换为 192x192 分辨率
3. 复制 annotation.proto
4. 按 delta_force_data 结构保存

使用方法：
    python3 scripts/preprocess_data_ubuntu.py [--batch-size N] [--clean]
    
参数：
    --batch-size N  每个batch文件夹中的数据数量（默认1）
    --clean         处理前清理旧数据
    --dry-run       仅显示将要处理的数据，不实际处理

作者：AI Assistant
"""

import os
import sys
import shutil
import logging
import subprocess
import argparse
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


def process_data_dirs(data_dirs: list, output_dir: str, batch_size: int = 1) -> dict:
    """
    处理所有数据目录，转换为目标结构
    
    Args:
        data_dirs: 有效数据目录列表
        output_dir: 输出根目录
        batch_size: 每个batch文件夹中的数据数量
    
    Returns:
        处理统计 {"success": int, "failed": int}
    """
    os.makedirs(output_dir, exist_ok=True)
    
    stats = {"success": 0, "failed": 0}
    
    batch_idx = 0
    data_idx = 0
    batch_dir = None
    
    total = len(data_dirs)
    logger.info(f"开始处理 {total} 个数据目录...")
    
    for src_dir_path in data_dirs:
        dir_name = os.path.basename(src_dir_path)
        
        # 创建批次目录 (每 batch_size 个数据创建一个 batch)
        if data_idx % batch_size == 0:
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


def verify_output_structure(output_dir: str) -> dict:
    """
    验证输出目录结构
    
    Returns:
        {"total_batches": int, "total_data": int, "errors": list}
    """
    if not os.path.exists(output_dir):
        return {"total_batches": 0, "total_data": 0, "errors": ["输出目录不存在"]}
    
    stats = {"total_batches": 0, "total_data": 0, "errors": []}
    
    # 遍历所有batch目录
    for batch_name in sorted(os.listdir(output_dir)):
        batch_path = os.path.join(output_dir, batch_name)
        
        if not os.path.isdir(batch_path):
            continue
            
        stats["total_batches"] += 1
        
        # 遍历所有data目录
        for data_name in sorted(os.listdir(batch_path)):
            data_path = os.path.join(batch_path, data_name)
            
            if not os.path.isdir(data_path):
                continue
            
            stats["total_data"] += 1
            
            # 检查必需文件
            proto_path = os.path.join(data_path, 'annotation.proto')
            video_path = os.path.join(data_path, 'video.mp4')
            
            if not os.path.exists(proto_path):
                stats["errors"].append(f"{batch_name}/{data_name}: 缺少 annotation.proto")
            if not os.path.exists(video_path):
                stats["errors"].append(f"{batch_name}/{data_name}: 缺少 video.mp4")
    
    return stats


def print_structure(output_dir: str, max_display: int = 10):
    """打印目录结构"""
    if not os.path.exists(output_dir):
        logger.warning(f"目录不存在: {output_dir}")
        return
    
    logger.info(f"\n{'='*60}")
    logger.info(f"输出目录结构: {output_dir}")
    logger.info(f"{'='*60}")
    
    batch_dirs = sorted([d for d in os.listdir(output_dir) 
                        if os.path.isdir(os.path.join(output_dir, d))])
    
    logger.info(f"Batch 数量: {len(batch_dirs)}")
    
    for i, batch_name in enumerate(batch_dirs[:max_display]):
        batch_path = os.path.join(output_dir, batch_name)
        data_dirs = sorted([d for d in os.listdir(batch_path) 
                           if os.path.isdir(os.path.join(batch_path, d))])
        
        logger.info(f"\n{batch_name}/ ({len(data_dirs)} 个数据)")
        for data_name in data_dirs[:3]:  # 只显示前3个
            data_path = os.path.join(batch_path, data_name)
            files = os.listdir(data_path)
            logger.info(f"  ├── {data_name}/ ({', '.join(files)})")
        if len(data_dirs) > 3:
            logger.info(f"  └── ... 还有 {len(data_dirs) - 3} 个数据")
    
    if len(batch_dirs) > max_display:
        logger.info(f"\n... 还有 {len(batch_dirs) - max_display} 个 batch")
    
    # 验证结构
    logger.info(f"\n{'='*60}")
    stats = verify_output_structure(output_dir)
    logger.info(f"验证结果:")
    logger.info(f"  Batch 数量: {stats['total_batches']}")
    logger.info(f"  数据总数: {stats['total_data']}")
    if stats['errors']:
        logger.warning(f"  错误数: {len(stats['errors'])}")
        for error in stats['errors'][:5]:
            logger.warning(f"    - {error}")
    else:
        logger.info(f"  错误数: 0 ✓")
    logger.info(f"{'='*60}\n")


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Ubuntu 视频预处理脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=1,
        help="每个batch文件夹中的数据数量（默认1）"
    )
    parser.add_argument(
        "--clean", "-c",
        action="store_true",
        help="处理前清理旧数据"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="仅显示将要处理的数据，不实际处理"
    )
    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="仅验证现有输出目录结构"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=SOURCE_DIR,
        help=f"源目录（默认: {SOURCE_DIR}）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=OUTPUT_DIR,
        help=f"输出目录（默认: {OUTPUT_DIR}）"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("视频预处理脚本 - Ubuntu 版本")
    logger.info("=" * 60)
    
    # 如果只是验证现有结构
    if args.verify:
        print_structure(args.output)
        sys.exit(0)
    
    # 检查 ffmpeg
    if not check_ffmpeg():
        sys.exit(1)
    
    # 检查源目录
    if not os.path.exists(args.source):
        logger.error(f"源目录不存在: {args.source}")
        logger.info("请确保 Windows 共享目录已挂载到 /mnt/d/")
        sys.exit(1)
    
    logger.info(f"源目录: {args.source}")
    logger.info(f"输出目录: {args.output}")
    logger.info(f"目标分辨率: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    logger.info(f"批次大小: {args.batch_size} (每个batch中的数据数量)")
    logger.info("")
    
    # 清理旧数据
    if args.clean:
        if os.path.exists(args.output):
            logger.warning(f"即将删除目录: {args.output}")
            response = input("确认删除? (y/n): ").strip().lower()
            if response == 'y':
                shutil.rmtree(args.output)
                logger.info("已删除旧数据")
            else:
                logger.info("取消清理")
    else:
        # 显示现有结构
        if os.path.exists(args.output):
            logger.info("现有输出目录:")
            print_structure(args.output)
    
    # 获取有效数据目录
    data_dirs = get_valid_data_dirs(args.source)
    
    if not data_dirs:
        logger.warning("没有找到有效的数据目录")
        sys.exit(0)
    
    logger.info(f"找到 {len(data_dirs)} 个有效数据目录")
    logger.info("")
    
    # Dry run 模式
    if args.dry_run:
        logger.info("Dry run 模式 - 仅显示将要处理的数据:")
        for i, src_dir in enumerate(data_dirs[:10]):
            logger.info(f"  {i+1}. {os.path.basename(src_dir)}")
        if len(data_dirs) > 10:
            logger.info(f"  ... 还有 {len(data_dirs) - 10} 个")
        logger.info("")
        logger.info(f"将会创建:")
        estimated_batches = (len(data_dirs) + args.batch_size - 1) // args.batch_size
        logger.info(f"  - 约 {estimated_batches} 个 batch 目录")
        logger.info(f"  - {len(data_dirs)} 个 data 目录")
        sys.exit(0)
    
    # 确认继续
    response = input(f"是否开始处理? (y/n): ").strip().lower()
    if response != 'y':
        logger.info("已取消")
        sys.exit(0)
    
    # 处理数据
    logger.info("")
    stats = process_data_dirs(data_dirs, args.output, args.batch_size)
    
    # 输出结果
    logger.info("")
    logger.info("=" * 60)
    logger.info("处理完成!")
    logger.info(f"成功: {stats['success']}")
    logger.info(f"失败: {stats['failed']}")
    logger.info(f"输出目录: {args.output}")
    logger.info("=" * 60)
    
    # 显示最终结构
    print_structure(args.output)


if __name__ == "__main__":
    main()
