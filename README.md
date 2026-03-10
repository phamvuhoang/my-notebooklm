# my-notebooklm (kotaemon fork)

This repository is a fork of [Cinnamon/kotaemon](https://github.com/Cinnamon/kotaemon.git).

**Fork Repository URL:** `git@github.com:phamvuhoang/my-notebooklm.git`

An open-source clean & customizable RAG UI for chatting with your documents. This fork adds specialized support for **Google Drive as a knowledge base**, allowing you to sync your Drive documents directly into your RAG pipeline.

![Preview](https://raw.githubusercontent.com/Cinnamon/kotaemon/main/docs/images/preview-graph.png)

[Live Demo #1](https://huggingface.co/spaces/cin-model/kotaemon) |
[Live Demo #2](https://huggingface.co/spaces/cin-model/kotaemon-demo) |
[Online Install](https://cinnamon.github.io/kotaemon/online_install/) |
[Colab Notebook (Local RAG)](https://colab.research.google.com/drive/1eTfieec_UOowNizTJA1NjawBJH9y_1nn)

[User Guide](https://cinnamon.github.io/kotaemon/) |
[Developer Guide](https://cinnamon.github.io/kotaemon/development/) |
[Feedback](https://github.com/Cinnamon/kotaemon/issues) |
[Contact](mailto:kotaemon.support@cinnamon.is)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-31013/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
<a href="https://github.com/Cinnamon/kotaemon/pkgs/container/kotaemon" target="_blank">
<img src="https://img.shields.io/badge/docker_pull-kotaemon:latest-brightgreen" alt="docker pull ghcr.io/cinnamon/kotaemon:latest"></a>
![download](https://img.shields.io/github/downloads/Cinnamon/kotaemon/total.svg?label=downloads&color=blue)
<a href='https://huggingface.co/spaces/cin-model/kotaemon-demo'><img src='https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-blue'></a>
<a href="https://hellogithub.com/en/repository/d3141471a0244d5798bc654982b263eb" target="_blank"><img src="https://abroad.hellogithub.com/v1/widgets/recommend.svg?rid=d3141471a0244d5798bc654982b263eb&claim_uid=RLiD9UZ1rEHNaMf&theme=small" alt="Featured｜HelloGitHub" /></a>

---
<!-- start-intro -->

## Introduction

This project provides a functional RAG (Retrieval-Augmented Generation) UI for both end users and developers. This specific fork, **my-notebooklm**, enhances the original project with a seamless Google Drive integration.
<br>

```yml
+----------------------------------------------------------------------------+
| End users: Those who use apps built with `kotaemon`.                       |
| (You use an app like the one in the demo above)                            |
|     +----------------------------------------------------------------+     |
|     | Developers: Those who built with `kotaemon`.                   |     |
|     | (You have `import kotaemon` somewhere in your project)         |     |
|     |     +----------------------------------------------------+     |     |
|     |     | Contributors: Those who make `kotaemon` better.    |     |     |
|     |     | (You make PR to this repo)                         |     |     |
|     |     +----------------------------------------------------+     |     |
|     +----------------------------------------------------------------+     |
+----------------------------------------------------------------------------+
```

### For end users

- **Clean & Minimalistic UI**: A user-friendly interface for RAG-based QA.
- **Support for Various LLMs**: Compatible with LLM API providers (OpenAI, AzureOpenAI, Cohere, etc.) and local LLMs (via `ollama` and `llama-cpp-python`).
- **Easy Installation**: Simple scripts to get you started quickly.

### For developers

- **Framework for RAG Pipelines**: Tools to build your own RAG-based document QA pipeline.
- **Customizable UI**: See your RAG pipeline in action with the provided UI, built with <a href='https://github.com/gradio-app/gradio'>Gradio <img src='https://img.shields.io/github/stars/gradio-app/gradio'></a>.
- **Gradio Theme**: If you use Gradio for development, check out our theme here: [kotaemon-gradio-theme](https://github.com/lone17/kotaemon-gradio-theme).

## Key Features

- **Host your own document QA (RAG) web-UI**: Support multi-user login, organize your files in private/public collections, collaborate and share your favorite chat with others.

- **Organize your LLM & Embedding models**: Support both local LLMs & popular API providers (OpenAI, Azure, Ollama, Groq).

- **Hybrid RAG pipeline**: Sane default RAG pipeline with hybrid (full-text & vector) retriever and re-ranking to ensure best retrieval quality.

- **Multi-modal QA support**: Perform Question Answering on multiple documents with figures and tables support. Support multi-modal document parsing (selectable options on UI).

- **Advanced citations with document preview**: By default the system will provide detailed citations to ensure the correctness of LLM answers. View your citations (incl. relevant score) directly in the _in-browser PDF viewer_ with highlights. Warning when retrieval pipeline return low relevant articles.

- **Google Drive knowledge source**: Connect Google Drive with per-user OAuth or a configured service account, choose folders, and sync Drive content into the existing file index and retrieval flow.

- **Support complex reasoning methods**: Use question decomposition to answer your complex/multi-hop question. Support agent-based reasoning with `ReAct`, `ReWOO` and other agents.

- **Configurable settings UI**: You can adjust most important aspects of retrieval & generation process on the UI (incl. prompts).

- **Extensible**: Being built on Gradio, you are free to customize or add any UI elements as you like. Also, we aim to support multiple strategies for document indexing & retrieval. `GraphRAG` indexing pipeline is provided as an example.

![Preview](https://raw.githubusercontent.com/Cinnamon/kotaemon/main/docs/images/preview.png)

## Installation for macOS

For the best experience on macOS, we recommend using the provided setup scripts or the `uv` package manager.

### Step-by-Step Local Setup

1.  **Clone the repository**:
    ```bash
    git clone git@github.com:phamvuhoang/my-notebooklm.git
    cd my-notebooklm
    ```

2.  **Choose your installation method**:

    #### Method A: Using the macOS Helper Script (Recommended)
    This is the easiest way to get started. The script automatically sets up a local Miniconda environment, installs all dependencies (including PDF.js), and launches the app.
    ```bash
    bash scripts/run_macos.sh
    ```
    *Use this if you want a self-contained installation that doesn't mess with your system Python.*

    #### Method B: Using `uv` (Fastest for Developers)
    If you have `uv` installed, this is the quickest way to sync dependencies.
    ```bash
    # Create/update the local virtual environment
    uv sync
    
    # Activate and launch
    source .venv/bin/activate
    python app.py
    ```
    *Troubleshooting `uv`:*
    - If `uv` is not found, install it via `brew install uv` or follow [these steps](https://docs.astral.sh/uv/getting-started/installation/).
    - If `uv sync` fails due to Python version mismatches, ensure you have Python 3.10+ installed (e.g., via `brew install python@3.10`).

    #### Method C: Manual Setup (Fallback)
    If you prefer using standard `pip` or `conda`:
    ```bash
    # (Optional) Create a conda environment
    conda create -n kotaemon python=3.10
    conda activate kotaemon

    # Install dependencies
    pip install -e "libs/kotaemon[all]"
    pip install -e "libs/ktem"
    pip install -e .
    
    # Create .env from example
    cp .env.example .env
    
    # Launch
    python app.py
    ```

3.  **Access the WebUI**:
    Once the application starts, navigate to `http://localhost:7860/` in your browser.
    - Default credentials: `admin` / `admin`.

### Troubleshooting macOS Setup

- **Whitespace in Path**: If your project directory is in a path with spaces (e.g., `/Users/Name/My Projects/`), some scripts may fail. Move the project to a path without spaces.
- **Xcode Command Line Tools**: Ensure they are installed: `xcode-select --install`.
- **Python Version**: Ensure you are using Python 3.10 or 3.11. Python 3.12+ might have compatibility issues with some older dependencies.

---

## Google Drive Knowledge Base

The primary enhancement in this fork is the robust support for Google Drive as a primary source of knowledge. This feature allows users to treat their Google Drive folders as dynamic libraries for their RAG pipeline.

### Why Google Drive?
- **Seamless Document Management**: No need to manually download from Drive and upload to the UI.
- **Dynamic Syncing**: Keep your RAG knowledge up to date as you add or edit files in your Drive folders.
- **Centralized Storage**: Leverage your existing organization system in Google Drive.

### How it Works
The Google Drive integration is implemented as a first-class "Connector" within the `ktem` library. It hooks into the existing `FileIndex` flow, treating Drive files similarly to local files but with the ability to "Sync" on demand.

#### 1. Configuration
You can configure Google Drive access in two ways via your `.env` file:

- **Per-User OAuth (Recommended for Multi-user)**:
  Users connect their own Google accounts through the UI.
  ```bash
  KH_GOOGLE_DRIVE_OAUTH_CLIENT_ID="your-client-id"
  KH_GOOGLE_DRIVE_OAUTH_CLIENT_SECRET="your-client-secret"
  KH_GOOGLE_DRIVE_OAUTH_REDIRECT_URI="http://127.0.0.1:8765/google-drive/callback"
  ```
- **Service Account (Recommended for Shared/Public Indexing)**:
  Uses a fixed service account to access specific shared folders.
  ```bash
  KH_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE="/path/to/service-account.json"
  KH_GOOGLE_DRIVE_SERVICE_ACCOUNT_SUBJECT="admin@yourdomain.com" # (Optional for domain-wide delegation)
  ```

#### 2. User Experience
1. Open a **File Collection** in the UI.
2. Switch to the **Google Drive** tab.
3. Authenticate with your Google account.
4. Browse and select the folders you want to include in your Knowledge Base.
5. Click **Sync Now**. The system will crawl the selected folders, download documents, parse them, and index them into the vector store.

### For Contributors
Architecturally, the integration adds:
- `GoogleDriveTab` in the Gradio UI for folder selection and authentication management.
- `GoogleDriveStateStore` to track which Drive files have been indexed and their last sync timestamps.
- Extended `IndexPipeline` methods to handle remote sources with metadata preservation.
- Secure token storage using the `cryptography` library for encrypted local caching of OAuth credentials (stored at `KH_GOOGLE_DRIVE_MASTER_KEY_PATH`).
- Multi-threaded sync logic to handle large folder structures efficiently.

### Default Models
This fork also updates the default Google AI models for improved performance:
- **LLM**: `gemini-2.5-flash`
- **Embedding**: `gemini-embedding-001`

### Setup GraphRAG

> [!NOTE]
> Official MS GraphRAG indexing only works with OpenAI or Ollama API.
> We recommend most users to use NanoGraphRAG implementation for straightforward integration with Kotaemon.

<details>

<summary>Setup Nano GRAPHRAG</summary>

- Install nano-GraphRAG: `pip install nano-graphrag`
- `nano-graphrag` install might introduce version conflicts, see [this issue](https://github.com/Cinnamon/kotaemon/issues/440)
  - To quickly fix: `pip uninstall hnswlib chroma-hnswlib && pip install chroma-hnswlib`
- Launch Kotaemon with `USE_NANO_GRAPHRAG=true` environment variable.
- Set your default LLM & Embedding models in Resources setting and it will be recognized automatically from NanoGraphRAG.

</details>

<details>

<summary>Setup LIGHTRAG</summary>

- Install LightRAG: `pip install git+https://github.com/HKUDS/LightRAG.git`
- `LightRAG` install might introduce version conflicts, see [this issue](https://github.com/Cinnamon/kotaemon/issues/440)
  - To quickly fix: `pip uninstall hnswlib chroma-hnswlib && pip install chroma-hnswlib`
- Launch Kotaemon with `USE_LIGHTRAG=true` environment variable.
- Set your default LLM & Embedding models in Resources setting and it will be recognized automatically from LightRAG.

</details>

<details>

<summary>Setup MS GRAPHRAG</summary>

- **Non-Docker Installation**: If you are not using Docker, install GraphRAG with the following command:

  ```shell
  pip install "graphrag<=0.3.6" future
  ```

- **Setting Up API KEY**: To use the GraphRAG retriever feature, ensure you set the `GRAPHRAG_API_KEY` environment variable. You can do this directly in your environment or by adding it to a `.env` file.
- **Using Local Models and Custom Settings**: If you want to use GraphRAG with local models (like `Ollama`) or customize the default LLM and other configurations, set the `USE_CUSTOMIZED_GRAPHRAG_SETTING` environment variable to true. Then, adjust your settings in the `settings.yaml.example` file.

</details>

### Setup Local Models (for local/private RAG)

See [Local model setup](docs/local_model.md).

### Setup multimodal document parsing (OCR, table parsing, figure extraction)

These options are available:

- [Azure Document Intelligence (API)](https://azure.microsoft.com/en-us/products/ai-services/ai-document-intelligence)
- [Adobe PDF Extract (API)](https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/)
- [Docling (local, open-source)](https://github.com/DS4SD/docling)
  - To use Docling, first install required dependencies: `pip install docling`

Select corresponding loaders in `Settings -> Retrieval Settings -> File loader`

### Customize your application

- By default, all application data is stored in the `./ktem_app_data` folder. You can back up or copy this folder to transfer your installation to a new machine.

- For advanced users or specific use cases, you can customize these files:

  - `flowsettings.py`
  - `.env`

#### `flowsettings.py`

This file contains the configuration of your application. You can use the example
[here](flowsettings.py) as the starting point.

<details>

<summary>Notable settings</summary>

```python
# setup your preferred document store (with full-text search capabilities)
KH_DOCSTORE=(Elasticsearch | LanceDB | SimpleFileDocumentStore)

# setup your preferred vectorstore (for vector-based search)
KH_VECTORSTORE=(ChromaDB | LanceDB | InMemory | Milvus | Qdrant)

# Enable / disable multimodal QA
KH_REASONINGS_USE_MULTIMODAL=True

# Setup your new reasoning pipeline or modify existing one.
KH_REASONINGS = [
    "ktem.reasoning.simple.FullQAPipeline",
    "ktem.reasoning.simple.FullDecomposeQAPipeline",
    "ktem.reasoning.react.ReactAgentPipeline",
    "ktem.reasoning.rewoo.RewooAgentPipeline",
]
```

</details>

#### `.env`

This file provides another way to configure your models and credentials.

<details>

<summary>Configure model via the .env file</summary>

- Alternatively, you can configure the models via the `.env` file with the information needed to connect to the LLMs. This file is located in the folder of the application. If you don't see it, you can create one.

- Currently, the following providers are supported:

  - **OpenAI**

    In the `.env` file, set the `OPENAI_API_KEY` variable with your OpenAI API key in order
    to enable access to OpenAI's models. There are other variables that can be modified,
    please feel free to edit them to fit your case. Otherwise, the default parameter should
    work for most people.

    ```shell
    OPENAI_API_BASE=https://api.openai.com/v1
    OPENAI_API_KEY=<your OpenAI API key here>
    OPENAI_CHAT_MODEL=gpt-3.5-turbo
    OPENAI_EMBEDDINGS_MODEL=text-embedding-ada-002
    ```

  - **Azure OpenAI**

    For OpenAI models via Azure platform, you need to provide your Azure endpoint and API
    key. Your might also need to provide your developments' name for the chat model and the
    embedding model depending on how you set up Azure development.

    ```shell
    AZURE_OPENAI_ENDPOINT=
    AZURE_OPENAI_API_KEY=
    OPENAI_API_VERSION=2024-02-15-preview
    AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-35-turbo
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT=text-embedding-ada-002
    ```

  - **Local Models**

    - Using `ollama` OpenAI compatible server:

      - Install [ollama](https://github.com/ollama/ollama) and start the application.

      - Pull your model, for example:

        ```shell
        ollama pull llama3.1:8b
        ollama pull nomic-embed-text
        ```

      - Set the model names on web UI and make it as default:

        ![Models](https://raw.githubusercontent.com/Cinnamon/kotaemon/main/docs/images/models.png)

    - Using `GGUF` with `llama-cpp-python`

      You can search and download a LLM to be ran locally from the [Hugging Face Hub](https://huggingface.co/models). Currently, these model formats are supported:

      - GGUF

        You should choose a model whose size is less than your device's memory and should leave
        about 2 GB. For example, if you have 16 GB of RAM in total, of which 12 GB is available,
        then you should choose a model that takes up at most 10 GB of RAM. Bigger models tend to
        give better generation but also take more processing time.

        Here are some recommendations and their size in memory:

      - [Qwen1.5-1.8B-Chat-GGUF](https://huggingface.co/Qwen/Qwen1.5-1.8B-Chat-GGUF/resolve/main/qwen1_5-1_8b-chat-q8_0.gguf?download=true): around 2 GB

        Add a new LlamaCpp model with the provided model name on the web UI.

  - **Google Drive**

    Configure one of the following before starting the app:

    ```shell
    # Per-user OAuth
    KH_GOOGLE_DRIVE_OAUTH_CLIENT_ID=
    KH_GOOGLE_DRIVE_OAUTH_CLIENT_SECRET=
    KH_GOOGLE_DRIVE_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/google-drive/callback

    # Or a service account for centralized/shared indexing
    KH_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
    KH_GOOGLE_DRIVE_SERVICE_ACCOUNT_SUBJECT=
    ```

    After launch, open a file collection, switch to the `Google Drive` tab, connect the account, refresh folders, select the folders you want, and run `Sync now`.

  </details>

### Adding your own RAG pipeline

#### Custom Reasoning Pipeline

1. Check the default pipeline implementation in [here](libs/ktem/ktem/reasoning/simple.py). You can make quick adjustment to how the default QA pipeline work.
2. Add new `.py` implementation in `libs/ktem/ktem/reasoning/` and later include it in `flowssettings` to enable it on the UI.

#### Custom Indexing Pipeline

- Check sample implementation in `libs/ktem/ktem/index/file/graph`

> (more instruction WIP).

<!-- end-intro -->

## Citation

Please cite this project as

```BibTeX
@misc{kotaemon2024,
    title = {Kotaemon - An open-source RAG-based tool for chatting with any content.},
    author = {The Kotaemon Team},
    year = {2024},
    howpublished = {\url{https://github.com/Cinnamon/kotaemon}},
}
```

## Star History

<a href="https://star-history.com/#Cinnamon/kotaemon&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Cinnamon/kotaemon&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Cinnamon/kotaemon&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Cinnamon/kotaemon&type=Date" />
 </picture>
</a>

## Contribution

Since our project is actively being developed, we greatly value your feedback and contributions. Please see our [Contributing Guide](https://github.com/Cinnamon/kotaemon/blob/main/CONTRIBUTING.md) to get started. Thank you to all our contributors!

<a href="https://github.com/Cinnamon/kotaemon/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Cinnamon/kotaemon" />
</a>

---

*Original project by the Kotaemon Team. Modified for enhanced Google Drive support by phamvuhoang.*
