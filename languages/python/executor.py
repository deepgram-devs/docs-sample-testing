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
        """Extract Python code samples from MDX files"""
        samples = []
        pages_path = documentation_path / self.framework_config['documentation']['pages_path']

        # Find all MDX files
        mdx_files = list(pages_path.rglob("*.mdx"))

        for mdx_file in mdx_files:
            try:
                content = mdx_file.read_text()
                file_samples = self._extract_python_samples_from_content(
                    str(mdx_file), content
                )
                samples.extend(file_samples)
            except Exception as e:
                print(f"Warning: Failed to process {mdx_file}: {e}")

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

        # Skip if it doesn't contain Deepgram-related imports
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
        """Execute Python code sample"""
        start_time = time.time()

        try:
            # Create test script
            test_script_path = self._create_test_script(sample, environment)

            # Set up environment
            test_env = os.environ.copy()
            test_env.update(environment['env_vars'])

            # Execute the script
            result = subprocess.run(
                [sys.executable, test_script_path],
                capture_output=True,
                text=True,
                timeout=self.framework_config.get('execution', {}).get('timeout_seconds', 30),
                env=test_env
            )

            execution_time = time.time() - start_time

            # Validate the sample
            validation_results = self.validate_sample(sample)

            return TestResult(
                sample=sample,
                success=result.returncode == 0,
                execution_time=execution_time,
                stdout=result.stdout,
                stderr=result.stderr,
                validation_results=validation_results
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                sample=sample,
                success=False,
                execution_time=time.time() - start_time,
                error_message="Test execution timed out",
                validation_results={}
            )
        except Exception as e:
            return TestResult(
                sample=sample,
                success=False,
                execution_time=time.time() - start_time,
                error_message=str(e),
                validation_results={}
            )

    def _create_test_script(self, sample: CodeSample, environment: Dict[str, Any]) -> str:
        """Create a standalone test script for the sample"""
        temp_dir = environment['temp_dir']
        script_path = os.path.join(temp_dir, f"test_sample_{sample.line_number}.py")

        # Clean and prepare the code
        code = self._prepare_code_for_execution(sample, environment)

        # Create test script content
        script_content = f'''#!/usr/bin/env python3
"""
Test script for code sample from {sample.file_path}
Line {sample.line_number}, Type: {sample.sample_type}
"""

import os
import sys
from pathlib import Path

# Add SDK path
import sys
import os
sys.path.insert(0, "{self.sdk_path.absolute()}")
# Also set PYTHONPATH environment variable for subprocess
os.environ["PYTHONPATH"] = "{self.sdk_path.absolute()}" + os.pathsep + os.environ.get("PYTHONPATH", "")

def main():
    try:
        # Original code sample (modified for testing)
{self._indent_code(code.strip(), 8)}

        print("✅ Code sample executed successfully")
        return True

    except ImportError as e:
        print(f"❌ Import error: {{e}}")
        return False
    except Exception as e:
        print(f"❌ Runtime error: {{e}}")
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

        # Remove migration guide comments
        code = re.sub(
            r'#\s*For help migrating.*?\n.*?#.*?/docs/Migrating.*?\n\s*',
            '',
            code,
            flags=re.MULTILINE
        )

        # Fix indentation: handle mixed indentation from MDX files
        import textwrap
        lines = code.split('\n')

        # First try textwrap.dedent (works if there's common leading whitespace)
        dedented = textwrap.dedent(code)

        # If dedent didn't change anything (mixed indentation), manually fix it
        if dedented == code:
            # Find non-empty, non-comment lines to determine base indentation
            code_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    code_lines.append(line)

            if code_lines:
                # Find minimum indentation of actual code lines
                min_indent = min(len(line) - len(line.lstrip()) for line in code_lines)

                # Remove that indentation from all lines
                fixed_lines = []
                for line in lines:
                    if len(line) > min_indent and line[:min_indent].isspace():
                        fixed_lines.append(line[min_indent:])
                    else:
                        fixed_lines.append(line.lstrip())  # Remove all leading space for lines with less indentation

                code = '\n'.join(fixed_lines)
            else:
                # No code lines found, just strip leading whitespace from all lines
                code = '\n'.join(line.lstrip() for line in lines)
        else:
            code = dedented

        # Replace placeholder API keys
        code = re.sub(r'"YOUR_API_KEY"', '"test_api_key"', code)
        code = re.sub(r"'YOUR_API_KEY'", "'test_api_key'", code)

        # Replace blocking operations that cause tests to hang
        code = re.sub(r'input\(\)', '"test_input"', code)  # Replace input() calls
        code = re.sub(r'input\(".*?"\)', '"test_input"', code)  # Replace input("...") calls
        code = re.sub(r'input\(\'.*?\'\)', '"test_input"', code)  # Replace input('...') calls

        # Replace infinite loops with limited loops for testing
        code = re.sub(r'while True:', 'for _ in range(1):', code)  # Replace while True with single iteration

        # Replace other blocking patterns commonly found in samples
        code = re.sub(r'time\.sleep\(\d+\)', 'time.sleep(0.1)', code)  # Reduce sleep times
        code = re.sub(r'connection\.start_listening\(\)', '# connection.start_listening()  # Skipped in tests', code)  # Skip websocket connections

        # Replace audio file references if mock file exists
        if 'mock_audio_path' in environment:
            mock_path = environment['mock_audio_path']
            code = re.sub(r'"[^"]*\\.(?:wav|mp3|m4a)"', f'"{mock_path}"', code)
            code = re.sub(r"'[^']*\\.(?:wav|mp3|m4a)'", f"'{mock_path}'", code)

        # Handle URLs that would make network calls
        code = re.sub(r'"https://dpgr\\.am/[^"]*"', '"https://example.com/test.wav"', code)

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
