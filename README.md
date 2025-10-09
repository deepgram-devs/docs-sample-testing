# Deepgram SDK Code Sample Documentation Testing Framework

A language-agnostic framework for testing code samples in SDK documentation during major version upgrades.

## 🎯 What This Framework Does

- **Extracts code samples** from MDX documentation files
- **Executes samples** in isolated environments with proper SDK dependencies
- **Validates syntax** and import correctness
- **Handles blocking operations** (input(), infinite loops, etc.)
- **Generates detailed reports** with actionable insights
- **Scales to hundreds of samples** across multiple documentation files

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/deepgram/docs-sample-testing.git
cd docs-sample-testing
pipenv install


```bash
# Test the framework setup
pipenv run python scripts/run_tests.py --help

```bash
# Run tests on Python samples (if you have the SDKs set up)
pipenv run python scripts/run_tests.py --language python --docs-path /path/to/docs
```

1. **Configure SDK and Documentation Paths**

   You have two options for configuration:

   ### Option A: Environment Variables (Recommended)
   ```bash
   # Set paths to your SDK repositories and documentation
   export PYTHON_SDK_PATH="/path/to/deepgram-python-sdk"
   export DOCS_PATH="/path/to/deepgram-fern-config"

   # Or create a .env file:
   echo "PYTHON_SDK_PATH=/path/to/deepgram-python-sdk" > .env
   echo "DOCS_PATH=/path/to/deepgram-fern-config" >> .env
   ```

   ### Option B: Command Line Arguments
   ```bash
   # Use --docs-path flag when running tests
   pipenv run python scripts/run_tests.py --language python --docs-path /path/to/docs
   ```

## 💡 Recommended Cursor Directory Structure

Based on which SDK code samples you want to test and update you can use the following structure in Cursor.

```
your-cursor-workspace/
├── docs-sample-testing/          # This repo
├── deepgram-docs/                # Documentation repo
├── deepgram-python-sdk/          # Python SDK repo
├── deepgram-js-sdk/              # JavaScript SDK repo
└── deepgram-go-sdk/              # Go SDK
└── deepgram-dotnet-sdk/          # .NET SDK
```

## 📁 Directory Structure

```
docs-sample-testing/
├── README.md                          # This documentation
├── config/
│   ├── framework_config.yaml          # Global settings (timeouts, paths, etc.)
│   └── languages/
│       ├── python.yaml                # Python SDK v5 patterns & validations
│       ├── javascript.yaml            # JavaScript config (placeholder)
│       ├── go.yaml                    # Go config (placeholder)
│       └── csharp.yaml                # C# config (placeholder)
├── core/
│   └── base_executor.py               # Abstract base class for language executors
├── languages/
│   ├── python/
│   │   └── executor.py                # Python-specific test execution logic
│   ├── javascript/
│   │   └── executor.js                # JavaScript executor (placeholder)
│   ├── go/
│   │   └── executor.go                # Go executor (placeholder)
│   └── csharp/
│       └── executor.py                # C# executor wrapper (placeholder)
├── scripts/
│   └── run_tests.py                   # Main test runner
├── samples-to-fix/
│   └── sample_files_to_fix.md         # History of SDK samples fixes made in Docs
└── test-runs/                         # Generated test reports (created on run)
```

## 🔧 How It Works

### 1. **Configuration**
- **Global settings** in `config/framework_config.yaml` (timeouts, file patterns)
- **Language-specific rules** in `config/languages/{lang}.yaml` (SDK patterns, imports)

### 2. **Sample Extraction**
- Parses MDX files to find code blocks by language tag (`\`\`\`python`, `\`\`\`javascript`, etc.)
- Handles complex indentation from MDX formatting
- Identifies sync vs async samples

### 3. **Test Execution**
- Creates temporary test scripts with proper imports and setup
- Handles blocking operations (replaces `input()`, `while True:`, etc.)
- Executes in isolated environment with SDK dependencies
- Applies configurable timeouts

### 4. **Validation & Reporting**
- Validates imports against known SDK patterns
- Checks for common migration issues
- Generates detailed JSON and Markdown reports
- Prioritizes issues by impact

## 🔮 Multi-Language Architecture

The framework is designed for easy expansion to other languages:

### Ready for Extension:
- **JavaScript/TypeScript**: Config file ready, executor placeholder in place
- **Go**: Config file ready, executor placeholder in place
- **C#/.NET**: Config file ready, executor wrapper in place
- **Any language**: Follow the same pattern using `base_executor.py`

### Adding a New Language:
1. **Create config**: `config/languages/{lang}.yaml` with patterns and rules
2. **Implement executor**: `languages/{lang}/executor.{ext}` following `base_executor.py` interface
3. **Test**: Run `scripts/run_tests.py --language {lang}`

## 📊 Reports Generated

### JSON Report (`test-runs/{language}_test_report.json`)
- Machine-readable results
- Detailed error information
- Execution times and metadata

### Markdown Report (`test-runs/{language}_test_report.md`)
- Human-readable summary
- Organized by sample type
- Prioritized recommendations

## 🎯 Best Practices Learned

1. **Start broad, then narrow**: Use semantic search to understand the codebase first
2. **Manual validation works**: Systematic file-by-file fixes are highly effective
3. **Framework complements manual work**: Use automation to identify issues, humans to fix them
4. **Handle edge cases**: Blocking operations, mixed indentation, legacy patterns
5. **Comprehensive testing**: Test complete workflows, not just syntax

## 📚 Documentation Files Preserved

- `python-samples/python_samples_to_fix.md` - Complete record of Python SDK v5 migration work


## 🐛 Troubleshooting

### Missing Dependencies
```bash
pipenv install --dev  # Install all dependencies including dev ones
```

### SDK Not Found
Make sure your `PYTHON_SDK_PATH` environment variable points to the correct directory containing the SDK source code.

### Documentation Not Found
Ensure your `DOCS_PATH` or `--docs-path` points to the directory containing MDX documentation files.

### Permission Issues
```bash
chmod +x scripts/run_tests.py
