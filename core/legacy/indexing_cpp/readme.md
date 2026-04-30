# PMET Indexing

PMET Indexing 是一个用于构建基因启动子序列 motif 索引的工具，通过分析 FIMO 输出结果生成高效的 k-mer 索引。

PMET Indexing is a tool for building motif indices of gene promoter sequences, generating efficient k-mer indices by analyzing FIMO output results.

## 功能特点 | Features

- **高效索引构建** | Efficient index construction
- **FIMO 结果解析** | FIMO result parsing
- **K-mer 分析** | K-mer analysis
- **批量处理支持** | Batch processing support

## 系统要求 | Requirements

- CMake 3.12+
- C++11 编译器 | C++11 compiler
- FIMO (MEME Suite)

## 快速开始 | Quick Start

### 1. 编译项目 | Build Project

```bash
bash build.sh
```

### 2. 运行流水线 | Run Pipeline

```bash
bash run.sh
```

## 项目结构 | Project Structure

```
pmet_indexing/
├── src/                    # 源代码 | Source code
│   ├── main.cpp
│   ├── cFimoFile.cpp
│   ├── cMotifHit.cpp
│   └── fastFileReader.cpp
├── data/                   # 数据文件 | Data files
│   ├── memefiles/          # MEME 文件 | MEME files
│   ├── promoters.fa        # 启动子序列 | Promoter sequences
│   ├── promoter_lengths.txt
│   └── promoters.bg        # 背景文件 | Background file
├── result/                 # 结果输出 | Output results
├── build.sh                # 构建脚本 | Build script
├── run.sh                  # 运行脚本 | Run script
└── CMakeLists.txt          # CMake 配置 | CMake configuration
```

## 参数说明 | Parameters

| 参数 Parameter | 说明 Description | 默认值 Default |
|----------------|------------------|----------------|
| `-f` | FIMO 结果目录 \| FIMO results directory | `result/fimo` |
| `-k` | K-mer 大小 \| K-mer size | `5` |
| `-n` | 顶级基因数量 \| Top genes count | `5000` |
| `-p` | 启动子长度文件 \| Promoter lengths file | - |
| `-o` | 输出目录 \| Output directory | `result` |

## 使用示例 | Usage Example

```bash
# 自定义参数运行 | Run with custom parameters
./build/pmetindex -f result/fimo -k 6 -n 3000 -p data/promoter_lengths.txt -o output
```

## 输出文件 | Output Files

- **索引文件** | Index files: 包含 k-mer 索引数据
- **统计报告** | Statistics report: 分析结果统计
- **日志文件** | Log files: 处理过程记录

## 故障排除 | Troubleshooting

### 常见问题 | Common Issues

1. **编译失败** | Compilation failed
   ```bash
   # 检查 CMake 版本 | Check CMake version
   cmake --version
   ```

2. **找不到可执行文件** | Executable not found
   ```bash
   # 重新编译 | Rebuild
   bash build.sh
   ```

3. **FIMO 命令未找到** | FIMO command not found
   ```bash
   # 安装 MEME Suite | Install MEME Suite
   ```

## 许可证 | License

MIT License

## 联系方式 | Contact

如有问题请提交 Issue | For issues, please submit an Issue