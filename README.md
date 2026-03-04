# UnrealMCP

<div align="center">

![UnrealMCP Banner](https://img.shields.io/badge/Unreal%20Engine-5.x-blue?style=for-the-badge&logo=unrealengine&logoColor=white)
![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-purple?style=for-the-badge)
![C++](https://img.shields.io/badge/C%2B%2B-17-blue?style=for-the-badge&logo=cplusplus&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Platforms](https://img.shields.io/badge/Platforms-Win64%20%7C%20Mac%20%7C%20Linux-lightgrey?style=for-the-badge)

**A powerful Model Context Protocol (MCP) plugin for Unreal Engine 5**  
*Bridge your AI assistant directly to the Unreal Editor*

</div>

---

## 📖 Overview

**UnrealMCP** is a full-featured Unreal Engine 5 plugin that implements the **Model Context Protocol (MCP)**, enabling AI agents like **Claude**, **Cursor**, or any MCP-compatible client to communicate directly with the Unreal Editor in real time.

The plugin is composed of two layers:
- **C++ Plugin** (`Source/`) — runs inside UE5 as an Editor Subsystem, hosts a TCP socket server, and handles all Unreal Engine API calls.
- **Python MCP Server** (`Python/`) — acts as the bridge between the MCP client and the C++ plugin, exposing tools over the MCP protocol.

---

## ✨ Features

### 🏗️ Blueprint Automation
| Feature | Description |
|---|---|
| Create Blueprints | Create new Blueprint classes from any parent class |
| Add Components | Add and configure components (StaticMesh, Collision, etc.) |
| Set Properties | Set component and physics properties programmatically |
| Compile Blueprints | Trigger Blueprint compilation from code |
| Material Management | Apply, query, and manage materials on actors and Blueprints |
| Blueprint Analysis | Analyze graph complexity and detect logic issues |

### 📊 Blueprint Graph Editing
| Feature | Description |
|---|---|
| Node Management | Add, delete, and move nodes in the Blueprint graph |
| Variable Management | Create, rename, and set properties on variables |
| Node Connections | Connect and disconnect pins between nodes |
| Event Management | Add and manage Event nodes |
| Function Editing | Create functions, add inputs/outputs, rename and delete |
| Control Flow | Add Branch, Sequence, ForLoop, and Switch nodes |
| Casting | Add Cast nodes for type-safe operations |
| Specialized Nodes | Add Timeline, Delay, DoOnce, and other utility nodes |

### 🌍 Procedural World Generation
| Generator | Description |
|---|---|
| 🏰 Castles | Full castles with outer/inner walls, keeps, towers, moats, and villages |
| 🏛️ Mansions | Detailed mansions with interior room layouts |
| 🏙️ Towns & Cities | Street grids, traffic lights, sidewalks, urban furniture, and utilities |
| 🌉 Bridges | Suspension bridge generation |
| 🏛️ Aqueducts | Roman-style aqueduct structures |
| 🏠 Houses | Varied residential building styles |
| 🌳 Vegetation | Organic tree generation using L-Systems |
| 🗺️ Dungeons | Procedural dungeon generation using Wave Function Collapse (WFC) |

### 🤖 AI & Navigation
| Feature | Description |
|---|---|
| AI Movement | Move AI pawns to locations or target actors |
| Behavior Trees | Run Behavior Trees on AI controllers |
| Blackboard | Read and write Blackboard values |
| Perception | Get AI perception info and register stimulus sources |
| EQS Queries | Execute Environment Query System queries |
| Navigation | Get random reachable points on the NavMesh |
| StateTree | Run, stop, and send events to StateTrees |
| Mass AI | Spawn and update Mass Entity crowds |

### 🛠️ Editor Automation
| Feature | Description |
|---|---|
| Actor Management | Spawn, delete, find, and transform actors |
| Python Execution | Run arbitrary Python scripts inside the Unreal Engine context |
| Asset Queries | List project assets and resources |
| Batch Commands | Execute multiple commands in a single request |

---

## 🗂️ Project Structure

```
UnrealMCP/
├── UnrealMCP.uplugin              # Plugin descriptor
│
├── Source/
│   └── UnrealMCP/
│       ├── UnrealMCP.Build.cs     # Build rules & module dependencies
│       ├── Public/                # Header files (.h)
│       │   ├── EpicUnrealMCPModule.h        # Module entry point
│       │   ├── EpicUnrealMCPBridge.h        # Main Editor Subsystem (TCP server host)
│       │   ├── MCPServerRunnable.h          # Background server thread
│       │   └── Commands/
│       │       ├── EpicUnrealMCPCommonUtils.h       # Shared JSON & actor utilities
│       │       ├── EpicUnrealMCPEditorCommands.h    # Actor spawn/delete/transform
│       │       ├── EpicUnrealMCPBlueprintCommands.h # Blueprint creation & materials
│       │       ├── EpicUnrealMCPBlueprintGraphCommands.h # Graph node editing
│       │       ├── EpicUnrealMCPAICommands.h        # AI & navigation commands
│       │       ├── EpicUnrealMCPStateTreeCommands.h # StateTree commands
│       │       ├── EpicUnrealMCPMassCommands.h      # Mass Entity commands
│       │       └── BlueprintGraph/
│       │           ├── NodeManager.h         # Add/find Blueprint nodes
│       │           ├── BPConnector.h         # Connect/disconnect pins
│       │           ├── BPVariables.h         # Variable CRUD
│       │           ├── EventManager.h        # Event node management
│       │           ├── NodeDeleter.h         # Delete nodes
│       │           ├── NodePropertyManager.h # Set node properties
│       │           ├── Function/
│       │           │   ├── FunctionManager.h # Create/delete/rename functions
│       │           │   └── FunctionIO.h      # Function inputs & outputs
│       │           └── Nodes/
│       │               ├── ControlFlowNodes.h    # Branch, Sequence, ForLoop
│       │               ├── CastingNodes.h        # Cast nodes
│       │               ├── UtilityNodes.h        # Print, delay, math nodes
│       │               ├── DataNodes.h           # Make/Break struct nodes
│       │               ├── SpecializedNodes.h    # Timeline, DoOnce, etc.
│       │               ├── AnimationNodes.h      # Animation-related nodes
│       │               ├── ExecutionSequenceEditor.h
│       │               ├── MakeArrayEditor.h
│       │               ├── SwitchEnumEditor.h
│       │               └── NodeCreatorUtils.h
│       │
│       └── Private/               # Implementation files (.cpp)
│           ├── EpicUnrealMCPModule.cpp
│           ├── EpicUnrealMCPBridge.cpp      # TCP server + command routing
│           ├── MCPServerRunnable.cpp         # Server thread loop
│           ├── Commands/                     # (mirrors Public/Commands/)
│           ├── ML/
│           │   └── MCPMLBridge.cpp          # ML inference bridge
│           ├── Mass/
│           │   └── MCPMassAIProcessor.cpp   # Mass Entity processor
│           └── Tasks/
│               └── MCPGameplayTask_AIAction.cpp # Async AI task
│
└── Python/
    ├── unreal_mcp_server_advanced.py  # Main MCP server (entry point)
    ├── config.py                      # Config management (env vars, pydantic)
    ├── requirements.txt               # Python dependencies
    ├── pyproject.toml                 # Project metadata (uv / setuptools)
    ├── .env.example                   # Environment variable template
    ├── docker-compose.yml             # Optional: Redis, Prometheus, Grafana
    ├── prometheus.yml                 # Prometheus scrape config
    ├── helpers/
    │   ├── infrastructure_creation.py # Town streets, lights, utilities
    │   ├── castle_creation.py         # Castle & fortress generation
    │   ├── mansion_creation.py        # Mansion layout & construction
    │   ├── house_construction.py      # Residential buildings
    │   ├── building_creation.py       # Generic building helpers
    │   ├── advanced_buildings.py      # Skyscrapers & complex structures
    │   ├── bridge_aqueduct_creation.py# Bridges & aqueducts
    │   ├── wave_function_collapse.py  # WFC dungeon generator
    │   ├── lsystem_generator.py       # L-System tree generator
    │   ├── blueprint_analysis.py      # Graph complexity & issue detection
    │   ├── actor_utilities.py         # Actor spawn & material helpers
    │   ├── actor_name_manager.py      # Safe actor name tracking
    │   ├── async_connection.py        # Async TCP connection layer
    │   ├── auth_manager.py            # JWT authentication manager
    │   ├── caching_layer.py           # In-memory & Redis caching
    │   ├── code_execution.py          # Sandboxed code execution
    │   ├── performance_monitor.py     # Metrics & telemetry
    │   ├── mcp_resources.py           # MCP resource providers
    │   ├── agent_memory.py            # Agent memory persistence
    │   └── blueprint_graph/           # Blueprint graph tool modules
    │       ├── node_manager.py
    │       ├── variable_manager.py
    │       ├── connector_manager.py
    │       ├── event_manager.py
    │       ├── node_deleter.py
    │       ├── node_properties.py
    │       ├── function_manager.py
    │       └── function_io.py
    ├── ml/
    │   └── mcp_rl_agent.py            # Reinforcement learning agent
    └── tests/
        ├── test_async_connection.py
        └── test_caching.py
```

---

## 🔧 Architecture

```
┌─────────────────────────────────────────────────────┐
│             AI Client (Claude / Cursor / etc.)       │
└──────────────────────┬──────────────────────────────┘
                       │ MCP Protocol (stdio / SSE)
┌──────────────────────▼──────────────────────────────┐
│          Python MCP Server                           │
│   unreal_mcp_server_advanced.py                      │
│   • Exposes tools via FastMCP                        │
│   • Manages connection pooling & retries             │
│   • Calls helper modules for complex generation      │
└──────────────────────┬──────────────────────────────┘
                       │ TCP Socket (127.0.0.1:55557)
                       │ JSON + 4-byte length framing
┌──────────────────────▼──────────────────────────────┐
│         C++ Plugin — UEpicUnrealMCPBridge            │
│   • Runs as UEditorSubsystem inside UE5              │
│   • Hosts TCP listener on a background thread        │
│   • Routes commands to handler classes               │
│   • Executes all UE API calls on the Game Thread     │
└──────────────────────┬──────────────────────────────┘
                       │ Unreal Engine 5 C++ API
┌──────────────────────▼──────────────────────────────┐
│              Unreal Editor / Runtime                 │
└─────────────────────────────────────────────────────┘
```

**Communication Protocol:**
- All messages are **length-prefixed**: a 4-byte big-endian `uint32` header followed by a UTF-8 JSON payload.
- Commands are JSON objects: `{ "type": "<command_name>", "params": { ... } }`
- Responses are JSON objects: `{ "status": "success" | "error", "result": { ... } }`
- Batch execution is supported: `{ "type": "batch", "params": { "commands": [...] } }`

---

## 📦 Installation

### Prerequisites
- Unreal Engine **5.x** (tested on UE 5.3 – 5.5)
- Python **3.10 – 3.13**
- `pip` or `uv` package manager

### Step 1 — Install the Plugin

Copy (or clone) the `UnrealMCP` folder into your project's `Plugins` directory:

```
YourProject/
└── Plugins/
    └── UnrealMCP/       ← place it here
```

### Step 2 — Enable the Plugin

1. Open your Unreal Engine project.
2. Go to **Edit → Plugins**.
3. Search for **UnrealMCP** and enable it.
4. Restart the editor when prompted.

The plugin will automatically start the TCP server on port **55557** when the editor loads.

### Step 3 — Install Python Dependencies

Navigate to the Python folder and install dependencies:

```bash
cd Plugins/UnrealMCP/Python

# Using pip
pip install -r requirements.txt

# OR using uv (recommended)
uv sync
```

> **Note:** Make sure you are using a Python environment accessible by your MCP client.

---

## ⚙️ Configuration

### Claude Desktop

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "unrealMCP": {
      "command": "python",
      "args": [
        "C:/Path/To/YourProject/Plugins/UnrealMCP/Python/unreal_mcp_server_advanced.py"
      ]
    }
  }
}
```

### Using `uv` (Recommended)

```json
{
  "mcpServers": {
    "unrealMCP": {
      "command": "uv",
      "args": [
        "--directory",
        "C:/Path/To/YourProject/Plugins/UnrealMCP/Python",
        "run",
        "unreal_mcp_server_advanced.py"
      ]
    }
  }
}
```

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
cp Python/.env.example Python/.env
```

Key settings:

| Variable | Default | Description |
|---|---|---|
| `UMCP_HOST` | `127.0.0.1` | Server host |
| `UMCP_PORT` | `55557` | TCP port (must match C++ plugin) |
| `UMCP_LOG_LEVEL` | `INFO` | Logging verbosity |
| `UMCP_ENABLE_AUTH` | `false` | Enable JWT authentication |
| `UMCP_ENABLE_CACHING` | `true` | Enable in-memory caching |
| `UMCP_REDIS_ENABLED` | `false` | Use Redis for caching |
| `UMCP_ENABLE_METRICS` | `true` | Enable Prometheus metrics |

---

## 🎮 Usage Examples

Once your AI client is connected, you can ask it to:

```
"Create a Blueprint called BP_Door that inherits from Actor."

"Add a StaticMeshComponent to BP_Door using the Door mesh."

"Generate a medieval castle at world location (0, 0, 0), medium size."

"Create a town with a 3x3 street grid centered at (500, 500, 0)."

"Analyze the Blueprint graph of BP_PlayerCharacter for complexity issues."

"Move the AI character BP_Enemy_1 to the location of BP_Target."

"Create a variable called 'Health' of type Float in BP_PlayerCharacter."

"Connect the OnComponentHit event to the ApplyDamage function in BP_Projectile."

"Generate a procedural dungeon using Wave Function Collapse at (0, 0, 0)."

"Spawn a tree using L-System generation at (200, 300, 0)."
```

---

## 🧩 Unreal Engine Dependencies

The plugin depends on the following UE5 modules:

| Module | Purpose |
|---|---|
| `UnrealEd`, `BlueprintGraph`, `KismetCompiler` | Blueprint editing |
| `AIModule`, `NavigationSystem` | AI & pathfinding |
| `GameplayTasks`, `GameplayTags` | Async task execution |
| `MassEntity`, `MassAI`, `MassGameplay` | Mass Entity (ECS) crowd simulation |
| `StateTreeModule`, `GameplayStateTreeModule` | Modern state machine AI |
| `Networking`, `Sockets`, `HTTP` | TCP communication |
| `Json`, `JsonUtilities` | JSON serialization |
| `EditorScriptingUtilities`, `PythonScriptPlugin` | Editor scripting |

---

## 🐳 Optional: Monitoring Stack

A `docker-compose.yml` is provided for optional monitoring infrastructure:

```bash
cd Plugins/UnrealMCP/Python
docker-compose up -d
```

| Service | URL | Description |
|---|---|---|
| Redis | `localhost:6379` | Caching backend |
| Prometheus | `http://localhost:9090` | Metrics collection |
| Grafana | `http://localhost:3000` | Metrics visualization (admin/admin) |

---

## 🧪 Running Tests

```bash
cd Plugins/UnrealMCP/Python

# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_async_connection.py -v
pytest tests/test_caching.py -v
```

---

## 📄 License

This project is licensed under the **MIT License**.

---

## 👤 Author

**Abdulrahman Faqe Salih**

---

<div align="center">

*Built with ❤️ for the Unreal Engine and AI community*

</div>
