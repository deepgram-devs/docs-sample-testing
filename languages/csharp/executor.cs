/*
 * C#/.NET SDK Test Executor
 * Example implementation showing how .NET executors could integrate
 *
 * This would be called by the Python test runner via subprocess
 */

using System;
using System.IO;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Diagnostics;

namespace Deepgram.Testing
{
    public class CodeSample
    {
        public string FilePath { get; set; } = "";
        public int LineNumber { get; set; }
        public string Code { get; set; } = "";
        public string Language { get; set; } = "csharp";
        public string SampleType { get; set; } = "";
        public List<string> Imports { get; set; } = new();
        public bool RequiresApiKey { get; set; }
        public bool RequiresAudioFile { get; set; }
        public Dictionary<string, object> Metadata { get; set; } = new();
    }

    public class TestResult
    {
        public CodeSample Sample { get; set; } = new();
        public bool Success { get; set; }
        public double ExecutionTime { get; set; }
        public string Stdout { get; set; } = "";
        public string Stderr { get; set; } = "";
        public string ErrorMessage { get; set; } = "";
        public Dictionary<string, bool> ValidationResults { get; set; } = new();
    }

    public class CSharpExecutor
    {
        private readonly Dictionary<string, object> _languageConfig;
        private readonly Dictionary<string, object> _frameworkConfig;

        public CSharpExecutor(Dictionary<string, object> languageConfig, Dictionary<string, object> frameworkConfig)
        {
            _languageConfig = languageConfig;
            _frameworkConfig = frameworkConfig;
        }

        public List<CodeSample> ExtractSamples(string documentationPath)
        {
            var samples = new List<CodeSample>();

            // Find MDX files and extract C# code blocks
            var pagesPath = Path.Combine(documentationPath, "fern", "pages");

            if (Directory.Exists(pagesPath))
            {
                var mdxFiles = Directory.GetFiles(pagesPath, "*.mdx", SearchOption.AllDirectories);

                foreach (var file in mdxFiles)
                {
                    try
                    {
                        var content = File.ReadAllText(file);
                        var fileSamples = ExtractCSharpSamplesFromContent(file, content);
                        samples.AddRange(fileSamples);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"Warning: Failed to process {file}: {ex.Message}");
                    }
                }
            }

            Console.WriteLine($"📝 Found {samples.Count} C# samples");
            return samples;
        }

        private List<CodeSample> ExtractCSharpSamplesFromContent(string filePath, string content)
        {
            var samples = new List<CodeSample>();

            // Regex patterns for C# code blocks
            var patterns = new[]
            {
                @"```csharp[^\n]*\n(.*?)```",
                @"```cs[^\n]*\n(.*?)```",
                @"```c#[^\n]*\n(.*?)```"
            };

            foreach (var pattern in patterns)
            {
                var matches = Regex.Matches(content, pattern, RegexOptions.Singleline);

                foreach (Match match in matches)
                {
                    var code = match.Groups[1].Value.Trim();

                    // Skip if too short or not Deepgram-related
                    if (code.Length < 30 || !code.ToLower().Contains("deepgram"))
                        continue;

                    // Calculate line number
                    var lineNumber = content.Substring(0, match.Index).Split('\n').Length;

                    var sample = new CodeSample
                    {
                        FilePath = filePath,
                        LineNumber = lineNumber,
                        Code = code,
                        SampleType = DetermineSampleType(code),
                        Imports = ExtractImports(code),
                        RequiresApiKey = RequiresApiKey(code),
                        RequiresAudioFile = RequiresAudioFile(code)
                    };

                    samples.Add(sample);
                }
            }

            return samples;
        }

        private string DetermineSampleType(string code)
        {
            if (code.Contains("async ") && code.Contains("await "))
                return "async";
            if (code.Contains("class ") && code.Contains("public "))
                return "class";
            if (code.Contains("Controller") || code.Contains("WebApi"))
                return "web";
            if (code.Contains("Console."))
                return "console";

            return "sync";
        }

        private List<string> ExtractImports(string code)
        {
            var imports = new List<string>();
            var matches = Regex.Matches(code, @"^using\s+[^;]+;", RegexOptions.Multiline);

            foreach (Match match in matches)
            {
                imports.Add(match.Value);
            }

            return imports;
        }

        private bool RequiresApiKey(string code)
        {
            var patterns = new[] { "apiKey", "DEEPGRAM_API_KEY", "DeepgramClient(" };
            return Array.Exists(patterns, p => code.Contains(p));
        }

        private bool RequiresAudioFile(string code)
        {
            var patterns = new[] { ".wav", ".mp3", "audioFile", "File.ReadAllBytes" };
            return Array.Exists(patterns, p => code.ToLower().Contains(p.ToLower()));
        }

        public Dictionary<string, bool> ValidateSample(CodeSample sample)
        {
            var results = new Dictionary<string, bool>();

            // Check for current vs deprecated patterns
            results["uses_current_namespace"] = sample.Code.Contains("using Deepgram;");
            results["no_old_imports"] = !sample.Code.Contains("using DeepgramSDK;");
            results["proper_client"] = sample.Code.Contains("new DeepgramClient");

            return results;
        }

        public TestResult ExecuteSample(CodeSample sample)
        {
            var stopwatch = Stopwatch.StartNew();

            try
            {
                // Create temporary project and execute
                var tempDir = Path.GetTempPath() + "dotnet-test-" + Guid.NewGuid().ToString("N")[..8];
                Directory.CreateDirectory(tempDir);

                var projectContent = CreateProjectFile();
                var programContent = PrepareCodeForExecution(sample);

                File.WriteAllText(Path.Combine(tempDir, "TestProject.csproj"), projectContent);
                File.WriteAllText(Path.Combine(tempDir, "Program.cs"), programContent);

                // Execute dotnet run
                var processInfo = new ProcessStartInfo
                {
                    FileName = "dotnet",
                    Arguments = "run",
                    WorkingDirectory = tempDir,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };

                processInfo.Environment["DEEPGRAM_API_KEY"] = "test_key";

                using var process = Process.Start(processInfo);
                process?.WaitForExit(30000); // 30 second timeout

                var success = process?.ExitCode == 0;
                var stdout = process?.StandardOutput.ReadToEnd() ?? "";
                var stderr = process?.StandardError.ReadToEnd() ?? "";

                // Cleanup
                try { Directory.Delete(tempDir, true); } catch { }

                return new TestResult
                {
                    Sample = sample,
                    Success = success,
                    ExecutionTime = stopwatch.Elapsed.TotalSeconds,
                    Stdout = stdout,
                    Stderr = stderr,
                    ValidationResults = ValidateSample(sample)
                };
            }
            catch (Exception ex)
            {
                return new TestResult
                {
                    Sample = sample,
                    Success = false,
                    ExecutionTime = stopwatch.Elapsed.TotalSeconds,
                    ErrorMessage = ex.Message
                };
            }
        }

        private string CreateProjectFile()
        {
            return """
                <Project Sdk="Microsoft.NET.Sdk">
                  <PropertyGroup>
                    <OutputType>Exe</OutputType>
                    <TargetFramework>net6.0</TargetFramework>
                  </PropertyGroup>
                  <ItemGroup>
                    <PackageReference Include="Deepgram" Version="*" />
                  </ItemGroup>
                </Project>
                """;
        }

        private string PrepareCodeForExecution(CodeSample sample)
        {
            var code = sample.Code;

            // Replace placeholders
            code = code.Replace("\"YOUR_API_KEY\"", "\"test_key\"");

            // Wrap in Main method if needed
            if (!code.Contains("static void Main") && !code.Contains("static async Task Main"))
            {
                if (code.Contains("await "))
                {
                    code = $"""
                        using System;
                        using System.Threading.Tasks;
                        using Deepgram;

                        class Program
                        {{
                            static async Task Main(string[] args)
                            {{
                                try
                                {{
                        {IndentCode(code, 12)}
                                    Console.WriteLine("✅ Code sample executed successfully");
                                }}
                                catch (Exception ex)
                                {{
                                    Console.WriteLine($"❌ Error: {{ex.Message}}");
                                }}
                            }}
                        }}
                        """;
                }
                else
                {
                    code = $"""
                        using System;
                        using Deepgram;

                        class Program
                        {{
                            static void Main(string[] args)
                            {{
                                try
                                {{
                        {IndentCode(code, 12)}
                                    Console.WriteLine("✅ Code sample executed successfully");
                                }}
                                catch (Exception ex)
                                {{
                                    Console.WriteLine($"❌ Error: {{ex.Message}}");
                                }}
                            }}
                        }}
                        """;
                }
            }

            return code;
        }

        private string IndentCode(string code, int spaces)
        {
            var lines = code.Split('\n');
            var indent = new string(' ', spaces);
            return string.Join('\n', Array.ConvertAll(lines, line =>
                string.IsNullOrWhiteSpace(line) ? line : indent + line));
        }
    }

    // CLI interface for integration with Python test runner
    class Program
    {
        static void Main(string[] args)
        {
            if (args.Length == 0)
            {
                Console.WriteLine("C# executor ready");
                return;
            }

            var command = args[0];
            Console.WriteLine($"C# executor: {command}");

            // This would handle JSON communication with Python test runner
            // For example, reading config and samples from stdin,
            // returning results as JSON to stdout
        }
    }
}
