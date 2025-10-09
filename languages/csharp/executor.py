#!/usr/bin/env python3
"""
C#/.NET SDK Test Executor
Implementation of BaseExecutor for .NET SDK testing
"""

import re
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import time
import shutil

# Add core to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))
from base_executor import BaseExecutor, CodeSample, TestResult


class CSharpExecutor(BaseExecutor):
    """.NET/C# specific implementation of the base executor"""

    def __init__(self, language_config: Dict[str, Any], framework_config: Dict[str, Any]):
        super().__init__(language_config, framework_config)
        self.sdk_path = Path(language_config['sdk']['repository_path'])
        self.package_name = language_config['sdk']['package_name']

    def extract_samples(self, documentation_path: Path) -> List[CodeSample]:
        """Extract C# code samples from MDX files"""
        samples = []
        pages_path = documentation_path / self.framework_config['documentation']['pages_path']

        # Find all MDX files
        mdx_files = list(pages_path.rglob("*.mdx"))

        for mdx_file in mdx_files:
            try:
                content = mdx_file.read_text()
                file_samples = self._extract_csharp_samples_from_content(
                    str(mdx_file), content
                )
                samples.extend(file_samples)
            except Exception as e:
                print(f"Warning: Failed to process {mdx_file}: {e}")

        return samples

    def _extract_csharp_samples_from_content(self, file_path: str, content: str) -> List[CodeSample]:
        """Extract C# code samples from MDX content"""
        samples = []

        # Pattern to find C# code blocks
        code_block_patterns = [
            r'```csharp[^\n]*\n(.*?)```',
            r'```cs[^\n]*\n(.*?)```',
            r'```c#[^\n]*\n(.*?)```',
            r'```dotnet[^\n]*\n(.*?)```'
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
                    language="csharp",
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
        if all(line.startswith('//') or line.startswith('/*') or line.startswith('*') for line in lines):
            return True

        # Skip if it doesn't contain Deepgram-related imports or usage
        deepgram_patterns = [
            'using Deepgram',
            'DeepgramClient',
            'Deepgram.',
            'deepgram'
        ]

        if not any(pattern.lower() in code.lower() for pattern in deepgram_patterns):
            return True

        return False

    def _determine_sample_type(self, code: str) -> str:
        """Determine the type of C# sample"""
        if "async " in code and "await " in code:
            return "async"
        elif "class " in code and "public " in code:
            return "class"
        elif "Controller" in code or "WebApi" in code:
            return "web"
        elif "Console." in code:
            return "console"
        else:
            return "sync"

    def _extract_imports(self, code: str) -> List[str]:
        """Extract using statements from code"""
        using_pattern = r'^using\s+[^;]+;'
        matches = re.findall(using_pattern, code, re.MULTILINE)
        return matches

    def _requires_api_key(self, code: str) -> bool:
        """Check if sample requires API key"""
        patterns = [
            "apiKey",
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
            "audioFile",
            "File.ReadAllBytes",
            "Transcribe.File"
        ]
        return any(pattern.lower() in code.lower() for pattern in patterns)

    def validate_sample(self, sample: CodeSample) -> Dict[str, bool]:
        """Validate C# sample against SDK patterns"""
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
        """Prepare .NET test environment"""
        temp_dir = tempfile.mkdtemp(prefix='dotnet-test-')

        env_info = {
            'temp_dir': temp_dir,
            'project_dir': temp_dir,
            'mock_files': [],
            'env_vars': self.create_mock_environment()
        }

        # Create mock audio file if needed
        if sample.requires_audio_file:
            mock_audio_path = self._create_mock_audio_file(temp_dir)
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
            f.write((44 - 8).to_bytes(4, byteorder='little'))
            f.write(b'WAVE')
            f.write(b'fmt ')
            f.write((16).to_bytes(4, byteorder='little'))
            f.write((1).to_bytes(2, byteorder='little'))
            f.write((1).to_bytes(2, byteorder='little'))
            f.write((44100).to_bytes(4, byteorder='little'))
            f.write((88200).to_bytes(4, byteorder='little'))
            f.write((2).to_bytes(2, byteorder='little'))
            f.write((16).to_bytes(2, byteorder='little'))
            f.write(b'data')
            f.write((0).to_bytes(4, byteorder='little'))

        return audio_path

    def execute_sample(self, sample: CodeSample, environment: Dict[str, Any]) -> TestResult:
        """Execute C# code sample"""
        start_time = time.time()

        try:
            # Create .NET project
            self._create_dotnet_project(sample, environment)

            # Set up environment
            test_env = os.environ.copy()
            test_env.update(environment['env_vars'])

            # Execute the project
            result = subprocess.run(
                ["dotnet", "run"],
                cwd=environment['project_dir'],
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

    def _create_dotnet_project(self, sample: CodeSample, environment: Dict[str, Any]) -> None:
        """Create a .NET console project for testing"""
        project_dir = environment['project_dir']

        # Create project file
        project_content = self._get_project_file_content()
        project_file = os.path.join(project_dir, "TestProject.csproj")
        with open(project_file, 'w') as f:
            f.write(project_content)

        # Create Program.cs with the sample code
        program_content = self._prepare_code_for_execution(sample, environment)
        program_file = os.path.join(project_dir, "Program.cs")
        with open(program_file, 'w') as f:
            f.write(program_content)

        # Initialize project (restore packages)
        try:
            subprocess.run(
                ["dotnet", "restore"],
                cwd=project_dir,
                capture_output=True,
                timeout=60  # Package restore might take longer
            )
        except subprocess.TimeoutExpired:
            print("Warning: Package restore timed out")

    def _get_project_file_content(self) -> str:
        """Get the content for the .csproj file"""
        return self.language_config.get('dotnet_patterns', {}).get('project_file_template', '''
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net6.0</TargetFramework>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Deepgram" Version="*" />
  </ItemGroup>
</Project>
''').strip()

    def _prepare_code_for_execution(self, sample: CodeSample, environment: Dict[str, Any]) -> str:
        """Prepare C# code sample for safe execution"""
        code = sample.code

        # Remove migration guide comments
        code = re.sub(
            r'//\s*For help migrating.*?\n.*?//.*?MIGRATION\.md.*?\n\s*',
            '',
            code,
            flags=re.MULTILINE
        )

        # Replace placeholder API keys
        code = re.sub(r'"YOUR_API_KEY"', '"test_api_key"', code)
        code = re.sub(r"'YOUR_API_KEY'", "'test_api_key'", code)

        # Replace audio file references if mock file exists
        if 'mock_audio_path' in environment:
            mock_path = environment['mock_audio_path'].replace('\\', '\\\\')  # Escape for C#
            code = re.sub(r'"[^"]*\\.(?:wav|mp3|m4a)"', f'"{mock_path}"', code)
            code = re.sub(r"'[^']*\\.(?:wav|mp3|m4a)'", f"'{mock_path}'", code)

        # Handle URLs that would make network calls
        code = re.sub(r'"https://dpgr\\.am/[^"]*"', '"https://example.com/test.wav"', code)

        # Ensure proper using statements are present
        required_usings = self.language_config.get('dotnet_patterns', {}).get('using_statements', [])
        existing_usings = self._extract_imports(code)

        usings_to_add = []
        for required in required_usings:
            if not any(required in existing for existing in existing_usings):
                usings_to_add.append(required)

        if usings_to_add:
            using_block = '\n'.join(usings_to_add) + '\n\n'
            code = using_block + code

        # Wrap in a proper Main method if needed
        if "static void Main" not in code and "static async Task Main" not in code:
            if "await " in code:
                # Async version
                code = f'''
using System;
using System.Threading.Tasks;
using Deepgram;

class Program
{{
    static async Task Main(string[] args)
    {{
        try
        {{
{self._indent_code(code, 12)}
            Console.WriteLine("✅ Code sample executed successfully");
        }}
        catch (Exception ex)
        {{
            Console.WriteLine($"❌ Error: {{ex.Message}}");
            Environment.Exit(1);
        }}
    }}
}}
'''
            else:
                # Sync version
                code = f'''
using System;
using Deepgram;

class Program
{{
    static void Main(string[] args)
    {{
        try
        {{
{self._indent_code(code, 12)}
            Console.WriteLine("✅ Code sample executed successfully");
        }}
        catch (Exception ex)
        {{
            Console.WriteLine($"❌ Error: {{ex.Message}}");
            Environment.Exit(1);
        }}
    }}
}}
'''

        return code

    def _indent_code(self, code: str, indent: int) -> str:
        """Indent code by specified number of spaces"""
        lines = code.split('\n')
        indented_lines = [' ' * indent + line if line.strip() else line for line in lines]
        return '\n'.join(indented_lines)

    def cleanup_test_environment(self, environment: Dict[str, Any]) -> None:
        """Clean up test environment"""
        # Remove temporary directory
        if 'temp_dir' in environment:
            try:
                shutil.rmtree(environment['temp_dir'])
            except Exception as e:
                print(f"Warning: Failed to cleanup temp dir: {e}")
