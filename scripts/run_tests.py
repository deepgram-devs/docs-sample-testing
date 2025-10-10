#!/usr/bin/env python3
"""
Universal SDK Documentation Testing Script

Runs tests for any supported language using the language-specific executor.

Usage:
    python run_tests.py --language python --docs-path ../deepgram-fern-config
    python run_tests.py --language javascript --docs-path ../deepgram-fern-config
    python run_tests.py --all-languages --docs-path ../deepgram-fern-config
"""

import sys
import argparse
import yaml
from pathlib import Path
from typing import Dict, Any, List
import importlib.util
import json

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from base_executor import BaseExecutor, TestResult


class TestRunner:
    """Universal test runner for all SDK languages"""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.framework_config = self._load_framework_config()
        self.supported_languages = self._discover_supported_languages()
        self.local_paths = self._load_local_paths()

    def _load_framework_config(self) -> Dict[str, Any]:
        """Load the main framework configuration"""
        config_path = self.config_dir / "framework_config.yaml"
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _discover_supported_languages(self) -> List[str]:
        """Discover which languages have configuration files"""
        languages_dir = self.config_dir / "languages"
        if not languages_dir.exists():
            return []

        languages = []
        for config_file in languages_dir.glob("*.yaml"):
            languages.append(config_file.stem)

        return languages

    def _load_local_paths(self) -> Dict[str, Any]:
        """Load local paths configuration if it exists"""
        local_config_path = Path(__file__).parent.parent / "local_paths.yaml"
        if local_config_path.exists():
            with open(local_config_path, 'r') as f:
                return yaml.safe_load(f)
        return {}

    def _load_language_config(self, language: str, sdk_path: str = None) -> Dict[str, Any]:
        """Load configuration for a specific language"""
        config_path = self.config_dir / "languages" / f"{language}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"No configuration found for language: {language}")

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Override SDK path if provided
        if sdk_path and 'sdk' in config:
            config['sdk']['repository_path'] = sdk_path

        return config

    def _get_executor_for_language(self, language: str) -> BaseExecutor:
        """Dynamically load the executor for a given language"""
        # Get SDK path from local config if available
        sdk_path = self.local_paths.get('sdk_paths', {}).get(language)
        language_config = self._load_language_config(language, sdk_path)

        # Import the language-specific executor
        executor_path = Path(__file__).parent.parent / "languages" / language / "executor.py"
        if not executor_path.exists():
            raise FileNotFoundError(f"No executor found for language: {language}")

        # Dynamically import the executor module
        spec = importlib.util.spec_from_file_location(f"{language}_executor", executor_path)
        executor_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(executor_module)

        # Find the executor class (assumes it ends with "Executor")
        executor_class = None
        for name in dir(executor_module):
            obj = getattr(executor_module, name)
            if (isinstance(obj, type) and
                issubclass(obj, BaseExecutor) and
                obj != BaseExecutor):
                executor_class = obj
                break

        if not executor_class:
            raise RuntimeError(f"No executor class found in {executor_path}")

        return executor_class(language_config, self.framework_config)

    def run_language_tests(self, language: str, docs_path: Path) -> List[TestResult]:
        """Run tests for a specific language"""
        print(f"🧪 Testing {language} samples...")

        executor = self._get_executor_for_language(language)

        # Extract samples
        print("  📝 Extracting code samples...")
        samples = executor.extract_samples(docs_path)
        print(f"     Found {len(samples)} {language} code samples")

        if not samples:
            print(f"  ⚠️  No {language} samples found")
            return []

        # Test each sample
        results = []
        for i, sample in enumerate(samples):
            print(f"  [{i+1}/{len(samples)}] Testing {Path(sample.file_path).name}:{sample.line_number}")

            if executor.should_skip_sample(sample):
                print(f"    ⏭️  Skipped (too small or comment-only)")
                continue

            try:
                # Prepare environment
                environment = executor.prepare_test_environment(sample)

                # Execute test
                result = executor.execute_sample(sample, environment)
                results.append(result)

                # Print immediate feedback
                if result.success:
                    print(f"    ✅ PASSED")
                else:
                    print(f"    ❌ FAILED")
                    if result.error_message:
                        print(f"       {result.error_message[:80]}...")
                    elif result.stderr:
                        print(f"       {result.stderr.strip()[:80]}...")

                # Cleanup
                executor.cleanup_test_environment(environment)

            except Exception as e:
                print(f"    ❌ EXCEPTION: {e}")
                # Create failed result for exception
                from base_executor import TestResult
                result = TestResult(
                    sample=sample,
                    success=False,
                    execution_time=0.0,
                    error_message=str(e)
                )
                results.append(result)

        return results

    def generate_report(self, language: str, results: List[TestResult]) -> Dict[str, Any]:
        """Generate a comprehensive report for language test results"""
        if not results:
            return {
                "language": language,
                "summary": {"total": 0, "passed": 0, "failed": 0},
                "results": []
            }

        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed

        # Group by sample type
        by_type = {}
        for result in results:
            sample_type = result.sample.sample_type
            if sample_type not in by_type:
                by_type[sample_type] = {"passed": 0, "failed": 0, "samples": []}

            if result.success:
                by_type[sample_type]["passed"] += 1
            else:
                by_type[sample_type]["failed"] += 1

            by_type[sample_type]["samples"].append({
                "file": Path(result.sample.file_path).name,
                "line": result.sample.line_number,
                "success": result.success,
                "execution_time": result.execution_time,
                "error": result.error_message or result.stderr.split('\n')[0] if result.stderr else ""
            })

        return {
            "language": language,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "success_rate": round(passed / total * 100, 1) if total > 0 else 0
            },
            "by_type": by_type,
            "results": [
                {
                    "file": Path(r.sample.file_path).name,
                    "line": r.sample.line_number,
                    "type": r.sample.sample_type,
                    "success": r.success,
                    "execution_time": r.execution_time,
                    "validation_results": r.validation_results,
                    "error": r.error_message or (r.stderr.split('\n')[0] if r.stderr else "")
                }
                for r in results
            ]
        }

    def save_report(self, language: str, report: Dict[str, Any], output_dir: Path):
        """Save test report in multiple formats"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON report
        json_path = output_dir / f"{language}_test_report.json"
        with open(json_path, 'w') as f:
            json.dump(report, f, indent=2)

        # Save Markdown report
        md_path = output_dir / f"{language}_test_report.md"
        self._save_markdown_report(report, md_path)

        print(f"📊 Reports saved:")
        print(f"   JSON: {json_path}")
        print(f"   Markdown: {md_path}")

    def _save_markdown_report(self, report: Dict[str, Any], output_path: Path):
        """Save a markdown version of the test report"""
        language = report["language"]
        summary = report["summary"]

        content = f"""# {language.title()} SDK Documentation Test Report

## Summary
- **Total samples tested:** {summary["total"]}
- **Passed:** {summary["passed"]} ({summary["success_rate"]}%)
- **Failed:** {summary["failed"]} ({100 - summary["success_rate"]:.1f}%)

## Results by Sample Type
"""

        for sample_type, stats in report["by_type"].items():
            content += f"""
### {sample_type.title()} Samples
- **Passed:** {stats["passed"]}
- **Failed:** {stats["failed"]}
"""

            if stats["failed"] > 0:
                content += "\n**Failed samples:**\n"
                for sample in stats["samples"]:
                    if not sample["success"]:
                        error = sample["error"][:100] + "..." if len(sample["error"]) > 100 else sample["error"]
                        content += f"- `{sample['file']}:{sample['line']}`: {error}\n"

        content += f"""
## Recommendations
1. **High Priority**: Fix failed sync/async samples (core functionality)
2. **Medium Priority**: Fix streaming samples (advanced features)
3. **Low Priority**: Fix integration examples (optional features)

*Report generated: {yaml.dump({'timestamp': 'now'}, default_flow_style=False).strip()}*
"""

        with open(output_path, 'w') as f:
            f.write(content)


def main():
    parser = argparse.ArgumentParser(description="Test SDK documentation code samples")
    parser.add_argument("--language", help="Language to test (python, javascript, go, etc.)")
    parser.add_argument("--all-languages", action="store_true", help="Test all supported languages")
    parser.add_argument("--docs-path", help="Path to documentation directory (overrides local config)")
    parser.add_argument("--output-dir", default="test-runs", help="Output directory for reports")
    parser.add_argument("--config-dir", default="config", help="Configuration directory")

    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    output_dir = Path(args.output_dir)

    if not config_dir.exists():
        print(f"❌ Configuration directory not found: {config_dir}")
        return 1

    runner = TestRunner(config_dir)

    # Determine docs path: command line arg takes precedence, then local config
    docs_path = None
    if args.docs_path:
        docs_path = Path(args.docs_path)
    elif runner.local_paths.get('docs_path'):
        docs_path = Path(runner.local_paths['docs_path'])
    else:
        print("❌ No documentation path specified!")
        print("   Either:")
        print("   1. Use --docs-path argument")
        print("   2. Create local_paths.yaml (copy from local_paths.yaml.example)")
        return 1

    if not docs_path.exists():
        print(f"❌ Documentation directory not found: {docs_path}")
        return 1

    # Determine which languages to test
    if args.all_languages:
        languages_to_test = runner.supported_languages
    elif args.language:
        if args.language not in runner.supported_languages:
            print(f"❌ Unsupported language: {args.language}")
            print(f"   Supported languages: {', '.join(runner.supported_languages)}")
            return 1
        languages_to_test = [args.language]
    else:
        print("❌ Must specify either --language or --all-languages")
        return 1

    print(f"🚀 Testing documentation samples for: {', '.join(languages_to_test)}")
    print(f"📁 Documentation path: {docs_path}")
    print(f"📊 Output directory: {output_dir}")
    print()

    overall_success = True

    for language in languages_to_test:
        try:
            results = runner.run_language_tests(language, docs_path)
            report = runner.generate_report(language, results)
            runner.save_report(language, report, output_dir)

            # Check if this language had failures
            if report["summary"]["failed"] > 0:
                overall_success = False

            print(f"✅ {language} testing complete: {report['summary']['passed']}/{report['summary']['total']} passed")

        except Exception as e:
            print(f"❌ Failed to test {language}: {e}")
            overall_success = False

        print()

    if overall_success:
        print("🎉 All tests completed successfully!")
        return 0
    else:
        print("⚠️  Some tests failed. Check reports for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
