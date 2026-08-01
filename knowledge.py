# -*- coding: utf-8 -*-
"""
knowledge.py — Windows C 盘空间占用知识库

每条规则：
  pattern : 相对盘符根的路径模式（不区分大小写，支持 * 通配，** 表示任意用户名等）
  title   : 这是什么
  desc    : 里面装的是什么东西
  safety  : safe    = 可放心清理，不影响系统
            caution = 可清理，但要用正确方法/有副作用
            danger  = 不要手动删，删了会出问题
            keep    = 系统必需，勿动
            user    = 你自己的文件，自己决定
  action  : 推荐的清理方法（命令或操作步骤）
"""

SAFETY_LABEL = {
    "safe":    ("✅ 可放心清理", "#22c55e"),
    "caution": ("⚠️ 可清理但需注意方法", "#eab308"),
    "danger":  ("🚫 不建议手动删除", "#f97316"),
    "keep":    ("🔒 系统必需，勿删", "#ef4444"),
    "user":    ("👤 个人文件，自行决定", "#3b82f6"),
}

# 注：pattern 里的 <user> 会匹配任意用户名
RULES = [
    # ============ Windows 系统核心 ============
    dict(pattern="Windows/WinSxS", title="Windows 组件存储 (WinSxS)",
         safety="danger",
         desc="Windows 系统组件仓库，存放所有系统文件的各个版本，用于系统更新、修复和回滚。"
              "看起来很大，但其中大量文件是硬链接，实际占用比显示的小。",
         action="绝不能手动删除文件！只能用官方命令压缩：以管理员运行 "
                "`Dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase`（通常能省 2~5 GB）"),
    dict(pattern="Windows/System32", title="Windows 系统核心文件", safety="keep",
         desc="操作系统本体，所有系统程序和驱动都在这里。", action="不要动"),
    dict(pattern="Windows/SysWOW64", title="32位兼容系统文件", safety="keep",
         desc="64 位 Windows 运行 32 位程序所需的系统文件。", action="不要动"),
    dict(pattern="Windows/SoftwareDistribution/Download", title="Windows 更新下载缓存",
         safety="safe",
         desc="Windows Update 下载的更新安装包。更新装完后这些文件就没用了。",
         action="可直接清空。或运行：`net stop wuauserv` 后删除内容，再 `net start wuauserv`"),
    dict(pattern="Windows/SoftwareDistribution", title="Windows 更新工作目录", safety="caution",
         desc="Windows Update 的下载缓存和数据库。其中 Download 子目录可清空。",
         action="只清理 Download 子目录，其他别动"),
    dict(pattern="Windows/Installer", title="Windows 安装程序缓存", safety="danger",
         desc="MSI 安装包缓存，卸载/修复/更新已装软件时需要用到。删除后部分软件将无法卸载或更新。",
         action="不要手动删。可用微软官方工具或 PatchCleaner 安全清理孤立安装包"),
    dict(pattern="Windows/Temp", title="系统临时文件", safety="safe",
         desc="系统和程序产生的临时文件，重启后大多无用。",
         action="可直接清空（正在使用的文件会跳过）"),
    dict(pattern="Windows/Prefetch", title="预读取缓存", safety="safe",
         desc="Windows 记录程序启动信息用来加速启动。删了会自动重建，短期内程序启动稍慢。",
         action="可删，但省不了多少空间，一般不值得"),
    dict(pattern="Windows/Logs", title="系统日志", safety="safe",
         desc="Windows 各组件的运行日志，仅用于排查问题。",
         action="可直接清理（CBS 日志有时会异常膨胀到几十 GB）"),
    dict(pattern="Windows/LiveKernelReports", title="内核错误报告", safety="safe",
         desc="系统内核异常时生成的转储文件，仅用于故障分析。", action="可直接删除"),
    dict(pattern="Windows/Minidump", title="蓝屏小转储文件", safety="safe",
         desc="蓝屏时保存的内存快照，用于分析蓝屏原因。不排查问题就没用。", action="可直接删除"),
    dict(pattern="Windows/MEMORY.DMP", title="蓝屏完整内存转储", safety="safe",
         desc="蓝屏时的完整内存镜像，可能有好几 GB。仅用于故障分析。", action="可直接删除"),
    dict(pattern="Windows/servicing", title="系统服务堆栈", safety="keep",
         desc="Windows 更新机制本身的组件。", action="不要动"),
    dict(pattern="Windows/assembly", title=".NET 全局程序集缓存", safety="keep",
         desc=".NET 程序运行所需的公共组件库。", action="不要动"),
    dict(pattern="Windows/Fonts", title="系统字体", safety="caution",
         desc="所有已安装字体。设计软件装的大字体包可能占不少空间。",
         action="可在 设置→字体 里卸载确定不用的第三方字体，系统自带字体别删"),
    dict(pattern="Windows", structural=True, title="Windows 系统目录", safety="keep",
         desc="操作系统所在目录。具体看子目录分析。", action="只清理下面标记为可清理的子目录"),

    # ============ 根目录大文件 ============
    dict(pattern="hiberfil.sys", title="休眠文件", safety="caution",
         desc="休眠功能的内存镜像文件，大小约为内存的 40%~100%。不用休眠功能的话纯属浪费。",
         action="如果你从不使用休眠：以管理员运行 `powercfg /h off` 即可自动删除（会同时关闭快速启动）"),
    dict(pattern="pagefile.sys", title="虚拟内存页面文件", safety="caution",
         desc="内存不够时系统把数据换出到这个文件。默认由系统自动管理大小。",
         action="不要直接删。内存 ≥32GB 可考虑在 系统→高级系统设置→性能→虚拟内存 里调小或移到 D 盘"),
    dict(pattern="swapfile.sys", title="UWP 应用交换文件", safety="keep",
         desc="商店应用（UWP）专用的交换文件，通常只有 16~256 MB。", action="不用管"),
    dict(pattern="DumpStack.log.tmp", title="内核转储堆栈日志", safety="keep",
         desc="系统崩溃转储机制的工作文件，很小。", action="不用管"),
    dict(pattern="Windows.old", title="旧版 Windows 备份", safety="safe",
         desc="系统大版本升级前的完整旧系统备份，用于回滚。升级后用着没问题就可以删。",
         action="设置→系统→存储→临时文件→勾选'以前的 Windows 安装'删除；或 `Dism /online /Cleanup-Image /StartComponentCleanup`"),
    dict(pattern="$Recycle.Bin", title="回收站", safety="safe",
         desc="所有用户删除但未清空的文件。", action="右键回收站→清空回收站"),
    dict(pattern="System Volume Information", title="系统还原点与卷影副本", safety="caution",
         desc="系统还原点、文件历史记录快照。权限保护，扫描工具通常读不到内部。",
         action="系统→系统保护→配置，可删除旧还原点或限制其最大占用"),
    dict(pattern="Recovery", title="系统恢复环境", safety="keep",
         desc="WinRE 恢复环境，系统出问题时的救命稻草，通常不到 1 GB。", action="不要动"),
    dict(pattern="PerfLogs", title="性能日志", safety="safe",
         desc="性能监视器的日志目录，通常是空的。", action="可删"),

    # ============ ProgramData ============
    dict(pattern="ProgramData/Package Cache", title="安装程序缓存 (Package Cache)", safety="danger",
         desc="Visual Studio、.NET、各类运行库的安装包缓存，修复/卸载时需要。",
         action="不建议手动删，删了以后相关软件无法修复或卸载"),
    dict(pattern="ProgramData/NVIDIA Corporation/Downloader", title="NVIDIA 驱动下载缓存", safety="safe",
         desc="GeForce Experience / NVIDIA App 下载的驱动安装包，装完就没用。", action="可直接清空"),
    dict(pattern="ProgramData/NVIDIA Corporation", title="NVIDIA 程序数据", safety="caution",
         desc="NVIDIA 驱动组件数据，其中 Downloader 子目录可清空。", action="只清 Downloader 子目录"),
    dict(pattern="ProgramData/Microsoft/Windows Defender", title="Windows Defender 数据", safety="caution",
         desc="病毒库、扫描历史和隔离区。Scans/History 有时膨胀。",
         action="一般不用动；异常大时可清理 Scans/History/Service/DetectionHistory"),
    dict(pattern="ProgramData/Microsoft/Search", title="Windows 搜索索引", safety="caution",
         desc="文件搜索索引数据库。删了会自动重建（重建期间搜索变慢、CPU占用高）。",
         action="过大时：设置→搜索→高级搜索索引设置→重建索引"),
    dict(pattern="ProgramData", structural=True, title="所有用户共享的程序数据", safety="caution",
         desc="各软件的共享数据、配置和缓存。具体看子目录。", action="按子目录分析"),

    # ============ Program Files ============
    dict(pattern="Program Files", structural=True, title="已安装的 64 位程序", safety="user",
         desc="你安装的软件本体。删除应通过'卸载'而不是直接删文件夹。",
         action="设置→应用→安装的应用，卸载不用的软件"),
    dict(pattern="Program Files (x86)", structural=True, title="已安装的 32 位程序", safety="user",
         desc="你安装的 32 位软件本体。", action="同上，通过卸载移除"),
    dict(pattern="Program Files/WindowsApps", title="商店应用本体", safety="danger",
         desc="Microsoft Store 应用的安装目录，权限严格保护。",
         action="通过 设置→应用 卸载不用的商店应用，别手动删"),

    # ============ 用户目录：缓存类（safe） ============
    dict(pattern="Users/<user>/AppData/Local/Temp", title="用户临时文件", safety="safe",
         desc="程序运行产生的临时文件，是 C 盘膨胀最常见的原因之一。",
         action="可直接清空（占用中的文件会自动跳过）"),
    dict(pattern="Users/<user>/AppData/Local/Google/Chrome/User Data/*/Cache*", title="Chrome 浏览器缓存",
         safety="safe", desc="网页缓存，删了不影响书签、密码、历史记录。",
         action="Chrome 设置→隐私→清除浏览数据→缓存的图片和文件"),
    dict(pattern="Users/<user>/AppData/Local/Google/Chrome/User Data", title="Chrome 用户数据",
         safety="caution", desc="包含书签、密码、扩展和缓存。缓存部分可清，其他是你的数据。",
         action="只通过浏览器内置的'清除浏览数据'清缓存"),
    dict(pattern="Users/<user>/AppData/Local/Microsoft/Edge/User Data", title="Edge 用户数据",
         safety="caution", desc="Edge 的书签、密码、扩展和缓存。",
         action="Edge 设置→隐私→清除浏览数据→缓存"),
    dict(pattern="Users/<user>/AppData/Local/Mozilla/Firefox", title="Firefox 缓存", safety="safe",
         desc="Firefox 网页缓存（配置和书签在 Roaming 下，这里只是缓存）。", action="可清"),
    dict(pattern="Users/<user>/AppData/Local/pip/cache", title="pip 下载缓存", safety="safe",
         desc="Python 包管理器 pip 下载过的安装包缓存，重新下载即可。", action="`pip cache purge` 或直接删"),
    dict(pattern="Users/<user>/AppData/Local/npm-cache", title="npm 缓存", safety="safe",
         desc="Node.js 包管理器的下载缓存（_cacache 是纯下载缓存随便删；_npx 里住着 npx 临时工具，"
              "若有 MCP 服务等正通过 npx 运行则暂缓）。清理器会自动预检占用。",
         action="`npm cache clean --force` 或直接删；提交清理时工具会自动检查占用"),
    dict(pattern="Users/<user>/AppData/Local/Yarn", title="Yarn 缓存", safety="safe",
         desc="Yarn 包管理器缓存。", action="`yarn cache clean` 或直接删"),
    dict(pattern="Users/<user>/AppData/Local/pnpm/store", title="pnpm 存储", safety="caution",
         desc="pnpm 的全局包存储，所有项目共享（硬链接），删了所有项目要重装依赖。",
         action="`pnpm store prune` 清理无引用的包"),
    dict(pattern="Users/<user>/AppData/Local/uv", title="uv 缓存", safety="safe",
         desc="Python uv 包管理器的缓存。注意：uvx 启动的工具（很多 MCP/AI 服务）会直接运行在缓存里，"
              "运行期间清理会导致它们崩溃。清理器会自动预检占用。",
         action="关闭 Claude Code/Cursor 等 AI 工具后运行 `uv cache clean`；或交给本工具（会自动检查占用）"),
    dict(pattern="Users/<user>/.gradle/caches", title="Gradle 构建缓存", safety="safe",
         desc="Android/Java 项目的依赖和构建缓存，重新构建时会重新下载。", action="可删，下次构建变慢"),
    dict(pattern="Users/<user>/.m2/repository", title="Maven 本地仓库", safety="safe",
         desc="Java Maven 依赖缓存。", action="可删，下次构建重新下载"),
    dict(pattern="Users/<user>/.nuget/packages", title="NuGet 包缓存", safety="safe",
         desc=".NET 项目依赖缓存。", action="`dotnet nuget locals all --clear`"),
    dict(pattern="Users/<user>/.cargo", title="Rust Cargo 缓存", safety="caution",
         desc="Rust 工具链的包缓存和已安装工具。registry 子目录可清。", action="`cargo cache -a`（需安装）或删 registry/cache"),
    dict(pattern="Users/<user>/.cache/huggingface", title="HuggingFace 模型缓存", safety="user",
         desc="下载的 AI 模型文件，单个模型可达几 GB~几十 GB。重新下载很耗时。",
         action="确定不用的模型可删：`huggingface-cli delete-cache`"),
    dict(pattern="Users/<user>/.ollama", title="Ollama 本地大模型", safety="user",
         desc="Ollama 下载的本地大语言模型，每个模型几 GB 到几十 GB。",
         action="`ollama list` 查看，`ollama rm 模型名` 删除不用的"),
    dict(pattern="Users/<user>/.conda", title="Conda 环境与包缓存", safety="caution",
         desc="Conda 虚拟环境和下载缓存。", action="`conda clean --all` 清缓存；不用的环境 `conda env remove`"),
    dict(pattern="Users/<user>/anaconda3/pkgs", title="Anaconda 包缓存", safety="safe",
         desc="Conda 下载的包缓存，已安装到环境里的不受影响。", action="`conda clean --all`"),
    dict(pattern="Users/<user>/AppData/Local/NVIDIA/GLCache", title="NVIDIA 着色器缓存", safety="safe",
         desc="游戏/图形程序编译好的着色器缓存，删了会自动重建（游戏首次加载稍慢）。", action="可直接删"),
    dict(pattern="Users/<user>/AppData/Local/D3DSCache", title="DirectX 着色器缓存", safety="safe",
         desc="DirectX 编译的着色器缓存，自动重建。", action="可直接删"),
    dict(pattern="Users/<user>/AppData/Local/CrashDumps", title="程序崩溃转储", safety="safe",
         desc="程序崩溃时的内存快照，仅用于开发者排查。", action="可直接删"),
    dict(pattern="Users/<user>/AppData/Local/Microsoft/Windows/Explorer", title="资源管理器缩略图缓存",
         safety="safe", desc="文件缩略图缓存，删了会重建。", action="磁盘清理工具勾选'缩略图'"),
    dict(pattern="Users/<user>/AppData/Local/Microsoft/Windows/INetCache", title="IE/旧版缓存",
         safety="safe", desc="旧版 IE 和部分程序的网络缓存。", action="可清"),

    # ============ 用户目录：软件数据（caution/user） ============
    dict(pattern="Users/<user>/AppData/Local/Docker", title="Docker Desktop 数据", safety="caution",
         desc="Docker 的虚拟磁盘（ext4.vhdx），装的镜像和容器都在里面，只增不减是通病。",
         action="先 `docker system prune -a` 清理无用镜像，再在 Docker Desktop 设置里压缩磁盘，"
                "或 `wsl --shutdown` 后用 `Optimize-VHD` 压缩"),
    dict(pattern="Users/<user>/AppData/Local/Packages", title="商店应用数据", safety="caution",
         desc="UWP/商店应用的用户数据和缓存（包括微信 UWP、截图工具等）。",
         action="卸载对应应用时自动清理；单个应用过大可在 设置→应用→高级选项→重置。"
                "注意：微信相关的应用不要重置，会丢聊天记录！"),
    dict(pattern="Users/<user>/AppData/Roaming/Tencent", title="腾讯系软件数据（QQ等）", safety="user",
         desc="QQ 等腾讯软件的聊天记录、图片视频缓存。聊天记录删了找不回。",
         action="在 QQ 设置里用'清理缓存'，别直接删文件夹"),
    dict(pattern="Users/<user>/Documents/WeChat Files", title="微信聊天数据", safety="user",
         desc="微信的聊天记录、接收的图片/视频/文件。删了聊天记录就找不回来！",
         action="不建议删。空间紧张时在微信里 设置→文件管理→更改目录 迁移到其他盘（数据不丢失）"),
    dict(pattern="Users/<user>/Documents/xwechat_files", title="微信(新版)聊天数据", safety="user",
         desc="新版微信的聊天记录和文件。删了聊天记录就找不回来！",
         action="不建议删。空间紧张时在微信里迁移存储目录到其他盘（数据不丢失）"),
    dict(pattern="Users/<user>/AppData/Local/Steam", title="Steam 本地缓存", safety="safe",
         desc="Steam 的着色器缓存和网页缓存（游戏本体不在这）。", action="可清，Steam 设置里也有清理入口"),
    dict(pattern="Users/<user>/AppData/Roaming/Adobe", title="Adobe 配置与缓存", safety="caution",
         desc="PS/PR/AE 等的配置和缓存。Common/Media Cache 可清。",
         action="在 PR/AE 里：编辑→首选项→媒体缓存→删除；配置文件别删"),
    dict(pattern="Users/<user>/AppData/Local/JetBrains", title="JetBrains IDE 缓存", safety="caution",
         desc="PyCharm/IDEA 等的索引和缓存，删了 IDE 要重新索引项目。",
         action="IDE 内 File→Invalidate Caches；旧版本残留目录可整个删"),
    dict(pattern="Users/<user>/AppData/Roaming/Code", title="VS Code 数据", safety="caution",
         desc="VS Code 配置、扩展数据和缓存。Cache/CachedData 可清。",
         action="清理 Cache、CachedData、CachedExtensionVSIXs 子目录"),
    dict(pattern="Users/<user>/AppData/Local/Programs", title="用户级安装的程序", safety="user",
         desc="装给当前用户的软件本体（VS Code、Chrome 等常装在这）。", action="通过卸载移除，别直接删"),
    dict(pattern="Users/<user>/AppData", structural=True, title="用户应用数据", safety="caution",
         desc="所有软件的用户数据、配置和缓存。按子目录分析。", action="按子目录分析"),
    dict(pattern="Users/<user>/AppData/Local", structural=True, title="本机应用数据（缓存为主）",
         safety="caution", desc="软件的本机数据和缓存，是 C 盘膨胀的重灾区。按子目录分析。",
         action="按子目录分析"),
    dict(pattern="Users/<user>/AppData/Roaming", structural=True, title="漫游应用数据（配置为主）",
         safety="caution", desc="软件的配置和数据（设计上可随账户漫游）。按子目录分析。",
         action="按子目录分析"),
    dict(pattern="Users/<user>/AppData/LocalLow", structural=True, title="低权限应用数据",
         safety="caution", desc="低完整性级别程序（部分浏览器插件、Unity 游戏存档等）的数据。",
         action="按子目录分析"),

    # ============ 用户目录：个人文件（user） ============
    dict(pattern="Users/<user>/Downloads", title="下载文件夹", safety="user",
         desc="你下载的所有文件。经常是安装包坟场——装完的安装包都可以删。",
         action="按大小排序，删掉不需要的安装包和旧文件，需要保留的移到 D 盘"),
    dict(pattern="Users/<user>/Desktop", title="桌面", safety="user",
         desc="桌面上的文件（真实占用空间在这）。", action="大文件移到 D 盘"),
    dict(pattern="Users/<user>/Documents", title="文档", safety="user",
         desc="你的文档，以及很多游戏存档/软件数据的默认位置。", action="自行整理，大文件移 D 盘"),
    dict(pattern="Users/<user>/Videos", title="视频", safety="user",
         desc="录屏软件（Xbox Game Bar、OBS）的默认保存位置，容易巨大。", action="移到 D 盘或删除"),
    dict(pattern="Users/<user>/Pictures", title="图片", safety="user", desc="你的图片。", action="移 D 盘"),
    dict(pattern="Users/<user>/Music", title="音乐", safety="user", desc="你的音乐。", action="移 D 盘"),
    dict(pattern="Users/<user>/OneDrive*", title="OneDrive 同步文件夹", safety="user",
         desc="云同步的本地副本。可以设置'仅联机可用'释放本地空间而不删云端文件。",
         action="右键文件夹→释放空间（Free up space），文件仍在云端"),

    # ============ 用户目录：结构性节点 ============
    dict(pattern="Users", structural=True, title="所有用户的个人文件夹", safety="user",
         desc="每个 Windows 账户的主目录都在这里，通常是 C 盘最大的占用来源。",
         action="看下级目录的具体分析"),
    dict(pattern="Users/<user>", structural=True, title="你的用户主目录", safety="user",
         desc="你的桌面、文档、下载、软件数据（AppData）全在这里。",
         action="看下级目录的具体分析"),
    dict(pattern="Users/Public", title="公共用户文件夹", safety="user",
         desc="所有账户共享的文件夹，一般很小。", action="有大文件可自行清理"),
    dict(pattern="Users/<user>/.vscode/extensions", title="VS Code 扩展", safety="caution",
         desc="已安装的 VS Code 扩展本体。老版本残留会累积。",
         action="VS Code 里卸载不用的扩展；目录里带旧版本号的重复文件夹可删"),
    dict(pattern="Users/<user>/.vscode", title="VS Code 用户端数据", safety="caution",
         desc="VS Code 扩展和 CLI 数据。", action="通过 VS Code 管理扩展"),
    dict(pattern="Drivers", title="预装驱动备份", safety="user",
         desc="品牌机/主板厂商预留的驱动安装包备份。系统正常运行不需要它，但重装驱动时方便。",
         action="确认驱动都能从官网下载后可删除，或整体移到 D 盘备用"),
    dict(pattern="Intel", title="Intel 驱动安装残留", safety="safe",
         desc="Intel 驱动安装程序解压的临时文件，装完即无用。", action="可删"),
    dict(pattern="AMD", title="AMD 驱动安装残留", safety="safe",
         desc="AMD 驱动安装程序解压的临时文件，装完即无用。", action="可删"),
    dict(pattern="NVIDIA", title="NVIDIA 驱动安装残留", safety="safe",
         desc="NVIDIA 驱动安装程序解压的临时文件（C:\\NVIDIA），装完即无用。", action="可删"),
    dict(pattern=".c-cleaner-quarantine", title="本工具的清理隔离区", safety="caution",
         desc="c-cleaner 清理时把文件先移到这里（可反悔）。里面是你已决定清理的内容。",
         action="在报告顶部点'清空隔离区'真正释放空间；或进入文件夹把误删的移回原位"),
    dict(pattern="OneDriveTemp", title="OneDrive 临时目录", safety="safe",
         desc="OneDrive 同步过程的临时文件。", action="可删"),
    dict(pattern="inetpub", title="IIS 网站根目录", safety="caution",
         desc="Windows 自带 Web 服务器（IIS）的目录，没启用 IIS 时基本是空的。", action="通常很小，不用管"),

    # ============ WSL / 虚拟机 ============
    dict(pattern="Users/<user>/AppData/Local/wsl", title="WSL 虚拟磁盘", safety="caution",
         desc="WSL Linux 子系统的虚拟磁盘文件，只增不减。",
         action="WSL 内清理文件后：`wsl --shutdown`，再 `Optimize-VHD -Path xxx.vhdx -Mode Full`（管理员）"),
    dict(pattern="Users/<user>/AppData/Local/Packages/*Ubuntu*", title="WSL Ubuntu 发行版", safety="caution",
         desc="通过商店安装的 WSL 发行版及其虚拟磁盘。",
         action="同上：内部清理后压缩 vhdx；不用的发行版 `wsl --unregister <名称>`"),
    dict(pattern="ProgramData/DockerDesktop", title="Docker Desktop 系统数据", safety="caution",
         desc="Docker Desktop 的虚拟磁盘和数据。", action="用 docker system prune 清理"),
]


# ---------- 个人保护规则（user_rules.json，优先级最高，不入 git） ----------
def _load_user_rules():
    """user_rules.json 里的 protected 条目 → keep 级规则，插到 RULES 最前。
    keep 级在 match_rule 里不可被社区规则覆盖，形成最高优先级。"""
    import os as _o
    import json as _j
    p = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "user_rules.json")
    try:
        with open(p, encoding="utf-8") as f:
            protected = _j.load(f).get("protected", [])
    except (OSError, _j.JSONDecodeError):
        return []
    rules = []
    for it in protected:
        if not it.get("pattern"):
            continue
        rules.append(dict(pattern=it["pattern"], title=it.get("title", it["pattern"]),
                          safety="keep",
                          desc=it.get("desc", "个人保护规则：保留勿删。"),
                          action=it.get("action", "保留，不要清理"),
                          user_protected=True))
    return rules


USER_PROTECTED = _load_user_rules()
RULES = USER_PROTECTED + RULES


def protected_titles():
    """给 AI 提示词用：用户要求永不删除的内容清单。"""
    return [r["title"] for r in USER_PROTECTED]


# ---------- Winapp2 社区规则库（可选，由 winapp2.py 生成） ----------
import os as _os
import json as _json
import fnmatch as _fnmatch

_W2_EXACT = {}   # 无通配符路径 -> 规则（O(1) 查找）
_W2_WILD = []    # (通配 pattern, 规则)，按长度降序


def _load_winapp2():
    p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                      "output", "winapp2_rules.json")
    try:
        with open(p, encoding="utf-8") as f:
            rules = _json.load(f)["rules"]
    except (OSError, _json.JSONDecodeError, KeyError):
        return
    for r in rules:
        pat = r["pattern"].replace("\\", "/").strip("/").lower()
        if any(c in pat for c in "*?["):
            _W2_WILD.append((pat, r))
        else:
            _W2_EXACT[pat] = r
    _W2_WILD.sort(key=lambda x: -len(x[0]))


_load_winapp2()


def _w2_lookup(p):
    r = _W2_EXACT.get(p)
    if r is not None:
        return r
    for pat, rule in _W2_WILD:
        if _fnmatch.fnmatch(p, pat):
            return rule
    return None


def match_rule(rel_path):
    """给定相对盘符根的路径（如 'Users/<用户名>/AppData/Local/Temp'），返回匹配的规则或 None。
    优先级：本地知识库 keep/danger 绝对优先 > 更具体（更长 pattern）者胜 > 本地库。"""
    import fnmatch
    p = rel_path.replace("\\", "/").strip("/").lower()
    parts = p.split("/")
    best = None
    best_len = -1
    for rule in RULES:
        pat = rule["pattern"].replace("\\", "/").lower()
        # <user> 通配用户名
        if "<user>" in pat and len(parts) >= 2 and parts[0] == "users":
            pat_filled = pat.replace("<user>", parts[1])
        else:
            pat_filled = pat
        if fnmatch.fnmatch(p, pat_filled):
            plen = len(pat_filled)
            if plen > best_len:
                best, best_len = rule, plen
    w2 = _w2_lookup(p)
    if w2 is None:
        return best
    if best is not None:
        if best["safety"] in ("keep", "danger"):   # 用户硬规则/系统保护，社区规则不可覆盖
            return best
        if best_len >= len(w2["pattern"]):
            return best
    return w2
