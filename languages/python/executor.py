#!/usr/bin/env python3
"""
Python SDK Test Executor
Implementation of BaseExecutor for Python SDK testing
"""

import re
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import time

# Add core to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))
from base_executor import BaseExecutor, CodeSample, TestResult


class PythonExecutor(BaseExecutor):
    """Python-specific implementation of the base executor"""

    def __init__(self, language_config: Dict[str, Any], framework_config: Dict[str, Any]):
        super().__init__(language_config, framework_config)
        self.sdk_path = Path(language_config['sdk']['repository_path']) / language_config['sdk']['source_path']

    def extract_samples(self, documentation_path: Path) -> List[CodeSample]:
        """Extract Python code samples from MDX files for content analysis"""
        samples = []
        pages_path = documentation_path / self.framework_config['documentation']['pages_path']

        # Find all MDX files
        mdx_files = list(pages_path.rglob("*.mdx"))

        for mdx_file in mdx_files:
            try:
                content = mdx_file.read_text()
                file_samples = self._extract_python_samples_for_analysis(
                    str(mdx_file), content
                )
                samples.extend(file_samples)
            except Exception as e:
                print(f"Warning: Failed to process {mdx_file}: {e}")

        return samples

    def _extract_python_samples_for_analysis(self, file_path: str, content: str) -> List[CodeSample]:
        """Extract Python code blocks from MDX for direct content analysis"""
        samples = []

        # Find Python code blocks with regex - much simpler approach
        import re

        # Pattern to match Python code blocks (```python or ```py)
        python_block_pattern = r'```(?:python|py)\n(.*?)\n```'

        for match in re.finditer(python_block_pattern, content, re.DOTALL):
            code_content = match.group(1)

            # Skip empty or very short blocks
            if not code_content.strip() or len(code_content.strip()) < 10:
                continue

            # Calculate line number in the original file
            lines_before = content[:match.start()].count('\n')
            line_number = lines_before + 1

            # Create sample for content analysis (don't clean/modify the code)
            sample = CodeSample(
                file_path=file_path,
                line_number=line_number,
                code=code_content,  # Keep original code for analysis
                language="python",
                sample_type="python_block",
                imports=[],  # Will analyze these later
                requires_api_key=True,  # Most Deepgram samples need API key
                requires_audio_file="audio" in code_content.lower(),
                metadata={}
            )
            samples.append(sample)

        return samples

    def _extract_python_samples_from_content(self, file_path: str, content: str) -> List[CodeSample]:
        """Extract Python code samples from MDX content"""
        samples = []

        # Pattern to find Python code blocks
        code_block_patterns = [
            r'```python[^\n]*\n(.*?)```',
            r'```py[^\n]*\n(.*?)```'
        ]

        for pattern in code_block_patterns:
            matches = re.finditer(pattern, content, re.DOTALL)

            for match in matches:
                code = match.group(1).strip()

                # Skip if too short or just comments
                if self._should_skip_code_block(code):
                    continue

                # Calculate line number
                line_number = content[:match.start()].count('\n') + 1

                # Analyze the sample
                sample_type = self._determine_sample_type(code)
                imports = self._extract_imports(code)
                requires_api_key = self._requires_api_key(code)
                requires_audio_file = self._requires_audio_file(code)

                sample = CodeSample(
                    file_path=file_path,
                    line_number=line_number,
                    code=code,
                    language="python",
                    sample_type=sample_type,
                    imports=imports,
                    requires_api_key=requires_api_key,
                    requires_audio_file=requires_audio_file,
                    metadata={}
                )

                samples.append(sample)

        return samples

    def _should_skip_code_block(self, code: str) -> bool:
        """Determine if a code block should be skipped"""
        if len(code.strip()) < 30:
            return True

        # Skip comment-only blocks
        lines = [line.strip() for line in code.split('\n') if line.strip()]
        if all(line.startswith('#') for line in lines):
            return True

        # Skip non-Python code patterns
        non_python_patterns = [
            'var ',  # JavaScript
            'let ',  # JavaScript
            'const ',  # JavaScript
            'new Credentials(',  # C#/JavaScript
            'using System',  # C#
            'namespace ',  # C#
            'public class',  # C#
            'private ',  # C#/Java
            'public ',  # C#/Java (when not in comments)
            'interface I',  # C# interface
        ]

        for pattern in non_python_patterns:
            if pattern in code and not any(line.strip().startswith('#') and pattern in line for line in lines):
                return True

        # Skip if it doesn't contain Deepgram-related imports or patterns
        deepgram_patterns = [
            'from deepgram import',
            'import deepgram',
            'DeepgramClient',
            'AsyncDeepgramClient'
        ]

        if not any(pattern in code for pattern in deepgram_patterns):
            return True

        return False

    def _determine_sample_type(self, code: str) -> str:
        """Determine the type of Python sample"""
        if "async def" in code or "await " in code or "AsyncDeepgramClient" in code:
            return "async"
        elif "class " in code and "def " in code:
            return "class"
        elif "websocket" in code.lower() or "WebSocket" in code:
            return "streaming"
        elif "def " in code:
            return "function"
        else:
            return "sync"

    def _extract_imports(self, code: str) -> List[str]:
        """Extract import statements from code"""
        import_pattern = r'^(from\s+\S+\s+import\s+.+|import\s+\S+.*?)$'
        matches = re.findall(import_pattern, code, re.MULTILINE)
        return matches

    def _requires_api_key(self, code: str) -> bool:
        """Check if sample requires API key"""
        patterns = [
            "api_key",
            "DEEPGRAM_API_KEY",
            "DEEPGRAM_TOKEN",
            "DeepgramClient("
        ]
        return any(pattern in code for pattern in patterns)

    def _requires_audio_file(self, code: str) -> bool:
        """Check if sample requires audio file"""
        patterns = [
            ".wav",
            ".mp3",
            ".m4a",
            "audio_file",
            "transcribe_file"
        ]
        return any(pattern.lower() in code.lower() for pattern in patterns)

    def validate_sample(self, sample: CodeSample) -> Dict[str, bool]:
        """Validate Python sample against SDK patterns"""
        results = {}
        validation_rules = self.get_validation_rules()

        for rule in validation_rules:
            rule_name = rule['name']
            check_pattern = rule['check']
            expected = rule.get('expected', False)

            pattern_found = bool(re.search(check_pattern, sample.code))

            if expected:
                # Pattern should be present
                results[rule_name] = pattern_found
            else:
                # Pattern should NOT be present
                results[rule_name] = not pattern_found

        return results

    def prepare_test_environment(self, sample: CodeSample) -> Dict[str, Any]:
        """Prepare Python test environment"""
        env_info = {
            'temp_dir': tempfile.mkdtemp(),
            'mock_files': [],
            'env_vars': self.create_mock_environment()
        }

        # Create mock audio file if needed
        if sample.requires_audio_file:
            mock_audio_path = self._create_mock_audio_file(env_info['temp_dir'])
            env_info['mock_files'].append(mock_audio_path)
            env_info['mock_audio_path'] = mock_audio_path

        return env_info

    def _create_mock_audio_file(self, temp_dir: str) -> str:
        """Create a mock audio file for testing"""
        audio_path = os.path.join(temp_dir, "test_audio.wav")

        # Create minimal WAV file header
        with open(audio_path, "wb") as f:
            # Basic WAV header (44 bytes)
            f.write(b'RIFF')
            f.write((44 - 8).to_bytes(4, byteorder='little'))  # File size - 8
            f.write(b'WAVE')
            f.write(b'fmt ')
            f.write((16).to_bytes(4, byteorder='little'))  # fmt chunk size
            f.write((1).to_bytes(2, byteorder='little'))   # Audio format (PCM)
            f.write((1).to_bytes(2, byteorder='little'))   # Number of channels
            f.write((44100).to_bytes(4, byteorder='little'))  # Sample rate
            f.write((88200).to_bytes(4, byteorder='little'))  # Byte rate
            f.write((2).to_bytes(2, byteorder='little'))   # Block align
            f.write((16).to_bytes(2, byteorder='little'))  # Bits per sample
            f.write(b'data')
            f.write((0).to_bytes(4, byteorder='little'))   # Data chunk size

        return audio_path

    def execute_sample(self, sample: CodeSample, environment: Dict[str, Any]) -> TestResult:
        """Analyze Python code sample and provide specific actionable feedback"""
        start_time = time.time()

        try:
            # Find specific issues in the sample
            findings = self._analyze_sample(sample)

            # Only "fail" if there are blocking issues (syntax errors, critical problems)
            has_blocking_issues = any(finding.get("blocking", False) for finding in findings)

            return TestResult(
                sample=sample,
                success=not has_blocking_issues,
                execution_time=time.time() - start_time,
                stdout=self._format_findings(findings),
                stderr="",
                validation_results={"findings": findings, "blocking_issues": has_blocking_issues}
            )

        except Exception as e:
            return TestResult(
                sample=sample,
                success=False,
                execution_time=time.time() - start_time,
                error_message=f"Analysis error: {str(e)}",
                validation_results={"analysis_error": True}
            )

    def _analyze_sample(self, sample: CodeSample) -> List[Dict[str, Any]]:
        """Find specific, actionable issues in code sample via content analysis"""
        findings = []
        code = sample.code
        file_name = Path(sample.file_path).name

        # Direct pattern analysis - no execution needed
        findings.extend(self._check_outdated_sdk_patterns(code, file_name))
        findings.extend(self._check_missing_imports(code))
        findings.extend(self._check_placeholder_patterns(code))
        findings.extend(self._check_best_practices(code))
        findings.extend(self._check_common_mistakes(code))

        return findings

    def _check_outdated_sdk_patterns(self, code: str, file_name: str) -> List[Dict[str, Any]]:
        """Check for outdated SDK patterns that are completely wrong"""
        findings = []

        # V2/V3 SDK patterns that are completely wrong in current docs
        if "from deepgram import Deepgram" in code:
            findings.append({
                "issue": "Outdated SDK Import (v2/v3)",
                "location": "Import statement",
                "problem": "Uses completely outdated import: `from deepgram import Deepgram`",
                "fix": "Change to: `from deepgram import DeepgramClient`",
                "impact": "Users will get ImportError - this class no longer exists",
                "blocking": True
            })

        if "Deepgram(" in code:
            findings.append({
                "issue": "Outdated Constructor (v2/v3)",
                "location": "Client instantiation",
                "problem": "Uses old constructor: `Deepgram(...)`",
                "fix": "Change to: `DeepgramClient(api_key=...)`",
                "impact": "Users will get NameError - this class no longer exists",
                "blocking": True
            })

        # Other v2/v3 patterns
        if "deepgram.transcription.prerecorded" in code:
            findings.append({
                "issue": "Outdated API Pattern (v2/v3)",
                "location": "API call",
                "problem": "Uses old API pattern: `deepgram.transcription.prerecorded`",
                "fix": "Change to: `deepgram.listen.prerecorded.v(version)`",
                "impact": "Users will get AttributeError - this API structure changed",
                "blocking": True
            })

        return findings

    def _check_missing_imports(self, code: str) -> List[Dict[str, Any]]:
        """Check for missing imports that would cause runtime errors"""
        findings = []

        # Core SDK imports
        if "DeepgramClient" in code and "from deepgram import DeepgramClient" not in code and "from deepgram import" not in code:
            findings.append({
                "issue": "Missing Core Import",
                "location": "Top of file",
                "problem": "Uses `DeepgramClient` without importing it",
                "fix": "Add: `from deepgram import DeepgramClient`",
                "impact": "Users will get NameError when trying to create client",
                "blocking": True
            })

        # Common missing standard library imports
        if ("os.getenv" in code or "os.environ" in code) and "import os" not in code:
            findings.append({
                "issue": "Missing Standard Import",
                "location": "Top of file",
                "problem": "Uses `os.getenv` or `os.environ` without importing os",
                "fix": "Add: `import os`",
                "impact": "Users will get NameError when accessing environment variables",
                "blocking": True
            })

        # Optional dependency patterns
        if "load_dotenv" in code and "from dotenv import load_dotenv" not in code:
            findings.append({
                "issue": "Missing Optional Import",
                "location": "Top of file",
                "problem": "Uses `load_dotenv()` without importing it",
                "fix": "Add: `from dotenv import load_dotenv` (and note it's optional)",
                "impact": "Users without python-dotenv will get ImportError",
                "blocking": False
            })

        return findings

    def _check_placeholder_patterns(self, code: str) -> List[Dict[str, Any]]:
        """Check for placeholder patterns that need improvement"""
        findings = []

        # API key placeholders
        if '"YOUR_API_KEY"' in code or "'YOUR_API_KEY'" in code:
            findings.append({
                "issue": "Placeholder API Key",
                "location": "Client configuration",
                "problem": "Uses placeholder string: `'YOUR_API_KEY'`",
                "fix": "Show environment variable pattern: `os.getenv('DEEPGRAM_API_KEY')`",
                "impact": "Users learn proper API key management from the start",
                "blocking": False
            })

        # File path placeholders
        if '"path/to/audio.wav"' in code or "'path/to/audio.wav'" in code:
            findings.append({
                "issue": "Placeholder File Path",
                "location": "File operations",
                "problem": "Uses placeholder path: `'path/to/audio.wav'`",
                "fix": "Use realistic example path or show how to get from user input",
                "impact": "Users understand how to provide actual file paths",
                "blocking": False
            })

        return findings

    def _check_best_practices(self, code: str) -> List[Dict[str, Any]]:
        """Check for opportunities to show best practices"""
        findings = []

        # Error handling for longer examples
        if "DeepgramClient" in code and "try:" not in code and len(code.split('\n')) > 10:
            findings.append({
                "issue": "Missing Error Handling",
                "location": "API calls",
                "problem": "Long example without error handling shown",
                "fix": "Add try/except block around API calls",
                "impact": "Users learn proper error handling patterns",
                "blocking": False
            })

        # Async/await patterns
        if "AsyncDeepgramClient" in code and "await" not in code:
            findings.append({
                "issue": "Async Pattern Issue",
                "location": "Async client usage",
                "problem": "Uses AsyncDeepgramClient but no await calls shown",
                "fix": "Show proper await usage with async client methods",
                "impact": "Users understand how to properly use async client",
                "blocking": True  # This would cause runtime errors
            })

        return findings

    def _check_common_mistakes(self, code: str) -> List[Dict[str, Any]]:
        """Check for common mistakes in documentation examples"""
        findings = []

        # Using sync and async clients together (confusing)
        if "DeepgramClient" in code and "AsyncDeepgramClient" in code:
            findings.append({
                "issue": "Mixed Client Types",
                "location": "Client usage",
                "problem": "Uses both sync and async clients in same example",
                "fix": "Show either sync OR async pattern, not both",
                "impact": "Reduces confusion about which client to use",
                "blocking": False
            })

        # Hardcoded URLs that might break
        if "https://api.deepgram.com" in code:
            findings.append({
                "issue": "Hardcoded API URL",
                "location": "Client configuration",
                "problem": "Hardcodes API URL instead of using default",
                "fix": "Remove explicit URL (use SDK default) or show as configuration option",
                "impact": "Prevents issues if API URL changes",
                "blocking": False
            })

        return findings

    def _format_findings(self, findings: List[Dict[str, Any]]) -> str:
        """Format findings for display"""
        if not findings:
            return "✅ No issues found - code looks good!"

        output = []
        blocking_issues = [f for f in findings if f.get("blocking", False)]
        suggestions = [f for f in findings if not f.get("blocking", False)]

        if blocking_issues:
            output.append(f"🚨 {len(blocking_issues)} issue(s) that prevent users from running this code:")
            for finding in blocking_issues:
                output.append(f"")
                output.append(f"**{finding['issue']}** ({finding['location']})")
                output.append(f"Problem: {finding['problem']}")
                output.append(f"Fix: {finding['fix']}")
                output.append(f"Impact: {finding['impact']}")

        if suggestions:
            if blocking_issues:
                output.append(f"\n" + "="*50)
            output.append(f"💡 {len(suggestions)} suggestion(s) to improve this example:")
            for finding in suggestions:
                output.append(f"")
                output.append(f"**{finding['issue']}** ({finding['location']})")
                output.append(f"Suggestion: {finding['fix']}")
                output.append(f"Why: {finding['impact']}")

        return "\n".join(output)

    def _create_test_script(self, sample: CodeSample, environment: Dict[str, Any]) -> str:
        """Create a standalone test script for the sample"""
        temp_dir = environment['temp_dir']
        script_path = os.path.join(temp_dir, f"test_sample_{sample.line_number}.py")

        # Clean and prepare the code
        code = self._prepare_code_for_execution(sample, environment)

        # Create test script content with better error handling
        script_content = f'''#!/usr/bin/env python3
"""
Test script for code sample from {sample.file_path}
Line {sample.line_number}, Type: {sample.sample_type}

Generated code for testing:
{self._indent_code(code.strip(), 0)[:300]}...
"""

import os
import sys
import traceback
from pathlib import Path

# Add SDK path
sys.path.insert(0, "{self.sdk_path.absolute()}")
# Also set PYTHONPATH environment variable for subprocess
os.environ["PYTHONPATH"] = "{self.sdk_path.absolute()}" + os.pathsep + os.environ.get("PYTHONPATH", "")

def main():
    try:
        sample_file = "{Path(sample.file_path).name}"
        sample_line = {sample.line_number}
        print(f"Testing code from {{sample_file}}:{{sample_line}}")

        # Original code sample (modified for testing)
{self._indent_code(code.strip(), 8)}

        print("✅ Code sample executed successfully")
        return True

    except SyntaxError as e:
        print(f"❌ Syntax error in generated code:")
        print(f"   Line {{e.lineno}}: {{e.text.strip() if e.text else 'Unknown'}}")
        print(f"   {{e.msg}}")
        return False
    except ImportError as e:
        print(f"❌ Import error: {{e}}")
        print("   Make sure the Deepgram SDK is installed and accessible")
        return False
    except Exception as e:
        print(f"❌ Runtime error: {{e}}")
        print("   Full traceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''

        # Write script file
        with open(script_path, 'w') as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)

        return script_path

    def _prepare_code_for_execution(self, sample: CodeSample, environment: Dict[str, Any]) -> str:
        """Prepare code sample for safe execution"""
        code = sample.code

        # Remove migration guide comments more carefully
        code = re.sub(
            r'#\s*For help migrating.*?\n.*?#.*?/docs/Migrating.*?\n\s*',
            '',
            code,
            flags=re.MULTILINE
        )

        # Better indentation handling
        code = self._fix_indentation(code)

        # Replace placeholder API keys more carefully
        code = re.sub(r'"YOUR_API_KEY"', '"test_api_key"', code)
        code = re.sub(r"'YOUR_API_KEY'", "'test_api_key'", code)
        # Handle environment variable patterns
        code = re.sub(r'os\.getenv\(["\']DEEPGRAM_API_KEY["\']\)', '"test_api_key"', code)
        code = re.sub(r'os\.environ\.get\(["\']DEEPGRAM_API_KEY["\']\)', '"test_api_key"', code)

        # Fix outdated imports (v2 -> v5 migration)
        code = re.sub(r'from deepgram import Deepgram\b', 'from deepgram import DeepgramClient', code)
        code = re.sub(r'\bDeepgram\(', 'DeepgramClient(', code)
        code = re.sub(r'\bDEEPGRAM_API_KEY\b', '"test_api_key"', code)

        # Replace blocking operations more carefully
        code = self._replace_blocking_operations(code)

        # Replace audio file references if mock file exists
        if 'mock_audio_path' in environment:
            code = self._replace_audio_file_paths(code, environment['mock_audio_path'])

        # Handle network URLs that would make calls
        code = re.sub(r'"https://dpgr\.am/[^"]*"', '"https://example.com/test.wav"', code)

        # Add necessary imports if missing
        code = self._add_missing_imports(code)

        # Handle function definitions that need to be wrapped
        code = self._handle_function_definitions(code)

        return code

    def _handle_function_definitions(self, code: str) -> str:
        """Handle function definitions that need special treatment for testing"""
        lines = code.split('\n')

        # Check if this code contains function definitions at the top level
        has_top_level_functions = any(
            line.strip().startswith('def ') and not line.startswith(' ')
            for line in lines
        )

        # Check if this code contains class definitions at the top level
        has_top_level_classes = any(
            line.strip().startswith('class ') and not line.startswith(' ')
            for line in lines
        )

        # If it has top-level function or class definitions, we need to handle them specially
        if has_top_level_functions or has_top_level_classes:
            # Instead of putting everything in main(), let the functions/classes be defined
            # at module level, then call them from main()
            return self._wrap_executable_code(code)

        return code

    def _wrap_executable_code(self, code: str) -> str:
        """Wrap executable code, keeping function/class definitions at module level"""
        lines = code.split('\n')
        definitions = []
        executable_lines = []

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if (stripped.startswith('def ') or stripped.startswith('class ')) and not line.startswith(' '):
                # This is a top-level function or class definition
                def_lines = [line]
                i += 1

                # Collect all lines that belong to this definition
                while i < len(lines) and (lines[i].startswith(' ') or not lines[i].strip()):
                    def_lines.append(lines[i])
                    i += 1

                definitions.extend(def_lines)
                continue
            elif stripped and not stripped.startswith('#') and not stripped.startswith('import') and not stripped.startswith('from '):
                # This looks like executable code
                executable_lines.append(line)
            else:
                # Comments, imports, empty lines - add to definitions (they go at module level)
                if stripped.startswith('import') or stripped.startswith('from ') or not stripped:
                    definitions.append(line)
                else:
                    executable_lines.append(line)

            i += 1

        # Combine: definitions at module level, executable code in main call
        result = '\n'.join(definitions)
        if executable_lines:
            if result.strip():
                result += '\n\n'
            result += '# Execute the main logic\n'
            result += '\n'.join(executable_lines)

        return result

    def _fix_indentation(self, code: str) -> str:
        """Fix indentation issues from MDX extraction - SIMPLIFIED"""
        import textwrap

        # Simple approach: just use textwrap.dedent which handles most cases well
        try:
            return textwrap.dedent(code).strip()
        except Exception:
            # If dedent fails for any reason, just return the original code
            return code.strip()

    def _replace_blocking_operations(self, code: str) -> str:
        """Replace blocking operations that cause tests to hang"""
        # Replace input() calls more carefully
        code = re.sub(r'\binput\(\s*\)', '"test_input"', code)
        code = re.sub(r'\binput\(\s*["\'][^"\']*["\']\s*\)', '"test_input"', code)

        # Replace infinite loops but preserve loop structure when possible
        # Only replace standalone 'while True:' not part of larger expressions
        code = re.sub(r'^(\s*)while\s+True\s*:\s*$', r'\1for _ in range(3):', code, flags=re.MULTILINE)

        # Reduce sleep times but don't eliminate them entirely
        code = re.sub(r'time\.sleep\(\s*\d+\s*\)', 'time.sleep(0.1)', code)
        code = re.sub(r'time\.sleep\(\s*\d*\.\d+\s*\)', 'time.sleep(0.1)', code)

        # Handle common blocking patterns more carefully
        code = re.sub(
            r'(\w+)\.start_listening\(\)',
            r'pass  # \1.start_listening() - skipped in tests',
            code
        )

        # Handle websocket connections
        code = re.sub(
            r'(\w+)\.connect\(\)',
            r'pass  # \1.connect() - skipped in tests',
            code
        )

        # Replace network calls that would fail in testing
        # Replace actual API calls with mock calls
        code = re.sub(
            r'(\w+)\.listen\.v1\.media\.transcribe_url\(',
            r'# \1.listen.v1.media.transcribe_url( - mocked\nprint("Mock transcription result"); response = type("obj", (object,), {"to_dict": lambda: {"results": {"channels": [{"alternatives": [{"transcript": "Mock transcription"}]}]}}})(); ',
            code
        )

        # Mock file operations that might fail
        code = re.sub(
            r'with open\(["\'][^"\']+["\']\s*,\s*["\']w[b]?["\']\)',
            r'with open("/tmp/mock_file.tmp", "w")',
            code
        )

        return code

    def _replace_audio_file_paths(self, code: str, mock_path: str) -> str:
        """Replace audio file paths with mock file path"""
        # Handle quoted file paths
        code = re.sub(r'"[^"]*\.(?:wav|mp3|m4a|flac|opus)"', f'"{mock_path}"', code)
        code = re.sub(r"'[^']*\.(?:wav|mp3|m4a|flac|opus)'", f"'{mock_path}'", code)

        # Handle file path variables
        code = re.sub(r'audio_file\s*=\s*["\'][^"\']+["\']', f'audio_file = "{mock_path}"', code)
        code = re.sub(r'file_path\s*=\s*["\'][^"\']+["\']', f'file_path = "{mock_path}"', code)

        return code

    def _add_missing_imports(self, code: str) -> str:
        """Add commonly missing imports and handle optional dependencies"""
        imports_to_add = []

        # Check for common imports that might be missing
        if 'time.sleep' in code and 'import time' not in code:
            imports_to_add.append('import time')

        if ('os.getenv' in code or 'os.environ' in code) and 'import os' not in code:
            imports_to_add.append('import os')

        if 'Path(' in code and 'from pathlib import Path' not in code:
            imports_to_add.append('from pathlib import Path')

        if 're.' in code and 'import re' not in code:
            imports_to_add.append('import re')

        # Handle optional dependencies with try/except imports
        optional_imports = []

        if 'load_dotenv' in code and 'from dotenv import' not in code:
            optional_imports.append('''try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        pass  # Mock implementation for testing''')

        if 'requests.' in code and 'import requests' not in code:
            optional_imports.append('''try:
    import requests
except ImportError:
    class MockRequests:
        @staticmethod
        def get(*args, **kwargs):
            class MockResponse:
                status_code = 200
                def json(self): return {"mock": "data"}
                def raise_for_status(self): pass
            return MockResponse()
    requests = MockRequests()''')

        if 'deepgram.utils' in code:
            optional_imports.append('''try:
    from deepgram.utils import verboselogs
except ImportError:
    class MockVerboseLogs:
        @staticmethod
        def info(*args): pass
        @staticmethod
        def debug(*args): pass
    verboselogs = MockVerboseLogs()''')

        # Combine all imports
        all_imports = []
        if imports_to_add:
            all_imports.extend(imports_to_add)
        if optional_imports:
            all_imports.extend(optional_imports)

        if all_imports:
            imports_section = '\n'.join(all_imports) + '\n\n'
            code = imports_section + code

        return code

    def _indent_code(self, code: str, indent: int) -> str:
        """Indent code by specified number of spaces"""
        lines = code.split('\n')
        indented_lines = [' ' * indent + line if line.strip() else line for line in lines]
        return '\n'.join(indented_lines)

    def _dedent_and_indent(self, code: str, indent: int) -> str:
        """Remove common leading whitespace, then indent properly"""
        import textwrap
        # First remove common leading whitespace
        dedented = textwrap.dedent(code)
        # Then add the proper indentation for the main() function
        lines = dedented.split('\n')
        indented_lines = [' ' * indent + line if line.strip() else line for line in lines]
        return '\n'.join(indented_lines)

    def _dedent_and_indent_properly(self, code: str, indent: int) -> str:
        """Properly handle code indentation for test scripts"""
        import textwrap

        # First, remove any common leading whitespace from the extracted code
        dedented = textwrap.dedent(code)

        # Split into lines and handle each one
        lines = dedented.split('\n')
        result_lines = []

        for line in lines:
            if line.strip():  # Non-empty line
                # Add the specified indentation
                result_lines.append(' ' * indent + line)
            else:  # Empty line
                result_lines.append('')  # Keep empty lines as-is

        return '\n'.join(result_lines)

    def cleanup_test_environment(self, environment: Dict[str, Any]) -> None:
        """Clean up test environment"""
        import shutil

        # Remove temporary directory
        if 'temp_dir' in environment:
            try:
                shutil.rmtree(environment['temp_dir'])
            except Exception as e:
                print(f"Warning: Failed to cleanup temp dir: {e}")
