# 智能体沙箱技术对比:gVisor / Firecracker / WASM

> 给学生看的入门指南。三种主流的"把不可信代码圈起来执行"的技术,各有特点和适用场景。

## 为什么智能体需要沙箱?

智能体调用工具时,可能执行的代码包括:
- 用户上传的脚本(数据分析、Excel 处理等)
- LLM 自己生成的代码(自动化运维、调试脚本等)
- 第三方插件/MCP server 内部的代码

这些代码都是**不完全可信**的——它们可能含 bug、可能被注入恶意指令、可能被供应链污染。**不能直接在主进程跑**——一个 `rm -rf /` 就完蛋。**必须在沙箱里跑**——隔离文件系统、网络、内存、CPU 等。

主流的三种工业级沙箱技术:

| | gVisor | Firecracker | WASM(WebAssembly) |
|---|---|---|---|
| **本质** | 用户态内核(syscall 拦截+模拟) | 轻量级虚拟机(microVM) | 二进制指令格式 + 沙箱运行时 |
| **隔离粒度** | 进程级(每个进程独立的内核) | 虚机级(完整 guest OS) | 函数/模块级 |
| **隔离强度** | 中(内核漏洞可能逃逸) | 高(虚机边界,等同 VM) | 极高(语言层面无法直接访问宿主) |
| **启动时间** | 100-300ms | 100-200ms | 1-10ms |
| **内存开销** | ~50-100MB/沙箱 | ~30-50MB/沙箱 | ~5-20MB/沙箱 |
| **支持的程序** | 几乎所有 Linux 程序 | 几乎所有 Linux 程序(只需 kernel) | 编译为 WASM 的程序(Rust/Go/AssemblyScript 等) |
| **典型用户** | Google Cloud Run、容器安全 | AWS Lambda、Fly.io | 浏览器、Cloudflare Workers、Fastly |
| **学习曲线** | 中(类 Docker 用法) | 中(类 KVM,需管 microVM) | 高(需要把代码编译为 WASM) |

---

## 1. gVisor

### 简介
Google 出的"用户态 Linux 内核"——在你的程序和真实内核之间插入一层"伪内核"(叫 Sentry),拦截所有 syscall,在用户态模拟实现,只把少量必要的 syscall 转发给真实内核。

### 工作原理
```
[Your Program]
     ↓ syscall
[gVisor Sentry (用户态内核)]   ← 拦截、模拟、过滤
     ↓ (少量必要的 syscall)
[Real Linux Kernel]
```

### 适用场景
- 跑**完整 Docker 容器**(替换默认 runc 即可,几乎无侵入)
- **遗留代码**——没源码的二进制也能跑
- 大规模容器编排——Google Cloud Run 用它跑 100 万级容器

### 装法
```bash
# Ubuntu
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list > /dev/null
sudo apt-get update && sudo apt-get install -y runsc
# Docker 配置
sudo runsc install
sudo systemctl restart docker
# 用 gVisor 起容器
docker run --runtime=runsc -it ubuntu bash
```

### 优缺点
- ✓ **完全 Linux 兼容**——任何 Linux 程序都能跑。
- ✓ **集成现有 Docker 工作流**——一行配置,无侵入。
- ✓ **内核安全性增强**——拦截层是核心防线。
- ✗ **Sentry 自身可能有漏洞**——历史上发生过逃逸 CVE,虽然修复快。
- ✗ **对部分 syscall 不支持**——少数依赖罕见系统调用的程序跑不动。
- ✗ **性能略损**——syscall 多的程序慢 10-20%。

---

## 2. Firecracker

### 简介
AWS 出的轻量级虚拟机管理器,基于 KVM,设计目标是"启动一个虚机像启动进程一样快"。Lambda 和 Fargate 的底层。

### 工作原理
```
[Your Program]
     ↓ 跑在 guest OS 里
[Linux Guest Kernel (在虚机里)]
     ↓
[Firecracker VMM (用户态)]
     ↓ KVM API
[Host Linux Kernel]
```
每个沙箱是独立的 microVM——独立的 kernel、独立的 root filesystem、独立的网卡。隔离强度等同传统虚机。

### 适用场景
- **高安全性 + 多租户**——AWS Lambda 一个 customer 一个 microVM。
- 跑**真正不可信的代码**——比如智能体调用 PyExecute 跑用户代码。
- 需要 **GPU/特殊设备**——可挂载到 microVM。

### 装法
```bash
# 下载 binary
wget https://github.com/firecracker-microvm/firecracker/releases/download/v1.7.0/firecracker-v1.7.0-x86_64.tgz
tar -xvf firecracker-v1.7.0-x86_64.tgz
# 准备 rootfs 和 kernel
# (这一步比较繁琐——需要构造 Linux kernel + rootfs image)
# 启动一个 microVM
./firecracker-v1.7.0-x86_64 --api-sock /tmp/firecracker.socket
# 通过 socket API 配置 boot params, drives, network 后启动
```
**实际生产建议用 firecracker-containerd 或 Fly.io 的封装**——直接手撸太繁琐。

### 优缺点
- ✓ **隔离最强**——virtual machine 等级,任何应用层逃逸都过不了 VM 边界。
- ✓ **启动快**(100-200ms,远快于 QEMU 的 5+s)。
- ✓ **资源占用极低**(30-50MB)——比 Docker 还低。
- ✗ **学习曲线高**——需要懂 kernel/rootfs 准备。
- ✗ **只支持 Linux KVM**——Mac/Windows 主机不能跑(开发环境麻烦)。
- ✗ **不能跑图形界面**——纯无头环境。

---

## 3. WASM(WebAssembly)

### 简介
不是"沙箱技术",而是一种**二进制指令格式 + 编译目标**——把代码编译为 WASM 字节码,然后用 WASM 运行时(wasmtime、wasmer、Spin、wazero)执行。运行时是天然沙箱化的(无 syscall、无文件系统访问、无网络,除非显式授予)。

### 工作原理
```
[Source Code (Rust / Go / C / AssemblyScript)]
     ↓ 编译
[WASM 字节码 (.wasm 文件)]
     ↓ 装载
[WASM Runtime (wasmtime / wasmer)]   ← 解释/JIT 执行
     ↓ (capabilities: 显式声明的 API)
[Host System]
```

### 适用场景
- **边缘/浏览器/插件**——Cloudflare Workers、Fastly Compute@Edge、扩展系统。
- **极致快启动 + 高密度**——单机 1 万+ 个并发实例(每个 5-20MB)。
- **跨平台**——同一 WASM 可在任何运行时跑。
- **新写智能体工具**——把工具实现为 WASM,沙箱化天然成立。

### 装法
```bash
# 安装 wasmtime
curl https://wasmtime.dev/install.sh -sSf | bash
# 编译一个 Rust 程序到 WASM
rustup target add wasm32-wasi
echo 'fn main() { println!("Hello WASM"); }' > hello.rs
rustc --target wasm32-wasi hello.rs -o hello.wasm
# 跑
wasmtime hello.wasm
# 显式授予文件系统访问
wasmtime --dir=. ./read_file.wasm
```

### 优缺点
- ✓ **隔离强度最高**——语言层面无法访问宿主资源,除非显式 capability。
- ✓ **极快启动**(1-10ms)和极低开销(5-20MB)。
- ✓ **跨平台、可移植**——同一 .wasm 跑遍 Linux/Mac/Windows。
- ✓ **天然多语言**——Rust/Go/C++/AssemblyScript 都能编译。
- ✗ **不是"任何 Linux 程序"——必须为 WASM target 编译**——遗留代码不能直接跑。
- ✗ **生态不如 Docker 成熟**——某些库还不支持。
- ✗ **不能直接调系统命令**——所有外部能力要通过 WASI(WebAssembly System Interface)显式 import。

---

## 我们项目里的选型建议

针对"政企智能体安全中台 + 运维协同助手"场景,我们的建议:

### 主选: gVisor
- 跑现有 Linux 工具(awk、grep、ssh、curl、kubectl)零修改。
- Docker 用户上手快,兼容运维同学的现有工作流。
- 性能损耗可接受(10-15%)。

### 辅助:WASM
- 我们**自研的工具**(如 Policy DSL 解释器、自动化运维插件)用 Rust 写,编译为 WASM。
- 这样:① 比 gVisor 更轻;② 跨平台分发简单;③ 可在浏览器 demo 里实时跑(炫!)。

### 备选:Firecracker
- 仅在"跑用户上传的完全不可信代码"场景启用。
- 工程量较大,MVP 阶段不做。

### 不选的方案
- **直接 Docker(runc)**——隔离不够强(共享 host kernel),不适合执行不可信代码。
- **Python subprocess + ulimit/seccomp**——粒度太粗,容易绕过,不推荐用于安全关键场景。
- **Nix sandbox / Bubblewrap**——好用但生态偏小众,部署适配麻烦。

## 学习路径

1. **第 1 天**:跑通 gVisor docker demo(`docker run --runtime=runsc`)。
2. **第 2 天**:用 wasmtime 跑一个 hello.wasm,理解 capability 模型。
3. **第 3 天**:设计我们 Policy DSL 解释器的 WASM 编译方案。
4. **第 4 天**:把 gVisor 集成到 LangChain 的 PythonREPL tool(让 LLM 生成的 python 在 gVisor 容器里跑)。
5. **第 5 天**:答辩 demo:展示同一段恶意脚本在 gVisor / 无沙箱下的不同效果。

## 参考资料

- gVisor 官网:https://gvisor.dev/
- Firecracker 项目:https://github.com/firecracker-microvm/firecracker
- WebAssembly:https://webassembly.org/
- wasmtime:https://wasmtime.dev/
- Bytecode Alliance(WASM 生态):https://bytecodealliance.org/
- 中文入门:[WebAssembly 中文站](https://wasmer.io/cn)、[gVisor 中文教程](https://www.qikqiak.com/post/runsc-introduction/)
