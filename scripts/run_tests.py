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

                # Print analysis results
                if result.success:
                    if "findings" in result.validation_results:
                        findings = result.validation_results["findings"]
                        if not findings:
                            print(f"    ✅ LOOKS GOOD")
                        else:
                            suggestions_count = len([f for f in findings if not f.get("blocking", False)])
                            print(f"    ✅ GOOD ({suggestions_count} suggestions)")
                    else:
                        print(f"    ✅ ANALYZED")
                else:
                    if "findings" in result.validation_results:
                        blocking_count = len([f for f in result.validation_results["findings"] if f.get("blocking", False)])
                        print(f"    🚨 NEEDS FIXES ({blocking_count} blocking issues)")
                    else:
                        print(f"    🔍 NEEDS ATTENTION")

                # Show immediate actionable feedback
                if result.stdout and result.stdout.strip():
                    # Show just the summary line for immediate feedback
                    lines = result.stdout.strip().split('\n')
                    if lines[0].startswith('🚨') or lines[0].startswith('💡'):
                        print(f"       {lines[0]}")

                # Show error if it's a real error (not analysis)
                if result.error_message and "Analysis error" in result.error_message:
                    print(f"       Error: {result.error_message}")

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

    def _get_full_error_message(self, result: TestResult) -> str:
        """Get a comprehensive error message for better troubleshooting"""
        if result.error_message:
            return result.error_message

        if result.stderr:
            # Return full stderr but limit to reasonable length for JSON
            stderr_lines = result.stderr.strip().split('\n')
            if len(stderr_lines) > 10:
                # Show first 8 lines and last 2 lines with ellipsis
                error_msg = '\n'.join(stderr_lines[:8])
                error_msg += '\n... (truncated) ...\n'
                error_msg += '\n'.join(stderr_lines[-2:])
                return error_msg
            else:
                return result.stderr.strip()

        if result.stdout and not result.success:
            return f"No stderr, but stdout: {result.stdout.strip()[:200]}"

        return "Unknown error - no error message or stderr available"

    def generate_report(self, language: str, results: List[TestResult]) -> Dict[str, Any]:
        """Generate a comprehensive report for language test results"""
        if not results:
            return {
                "language": language,
                "summary": {"total": 0, "passed": 0, "failed": 0, "success_rate": 0},
                "by_type": {},
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
                "error": self._get_full_error_message(result)
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
                    "error": self._get_full_error_message(r)
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
        """Save a markdown version of the analysis report"""
        language = report["language"]
        summary = report["summary"]

        # Collect findings data
        blocking_issues = []
        improvement_suggestions = []

        for result in report["results"]:
            if "validation_results" in result and "findings" in result["validation_results"]:
                findings = result["validation_results"]["findings"]

                for finding in findings:
                    finding_data = {
                        "file": result["file"],
                        "line": result["line"],
                        "issue": finding.get("issue", "Unknown Issue"),
                        "location": finding.get("location", "Unknown Location"),
                        "problem": finding.get("problem", "No details"),
                        "fix": finding.get("fix", "No fix provided"),
                        "impact": finding.get("impact", "Unknown impact")
                    }

                    if finding.get("blocking", False):
                        blocking_issues.append(finding_data)
                    else:
                        improvement_suggestions.append(finding_data)

        content = f"""# {language.title()} SDK Documentation Analysis Report

## Overview
- **Total samples analyzed:** {summary["total"]}
- **Samples ready to use:** {summary["passed"]} ({summary["success_rate"]}%)
- **Samples with blocking issues:** {len(blocking_issues)}
- **Samples with improvement opportunities:** {len(improvement_suggestions)}

## 🚨 Blocking Issues (Fix These First)

These issues prevent users from running the code successfully:

"""

        if blocking_issues:
            # Group by issue type for better organization
            issues_by_type = {}
            for issue in blocking_issues:
                issue_type = issue["issue"]
                if issue_type not in issues_by_type:
                    issues_by_type[issue_type] = []
                issues_by_type[issue_type].append(issue)

            for issue_type, issues in issues_by_type.items():
                content += f"### {issue_type} ({len(issues)} samples)\n\n"
                for issue in issues[:5]:  # Show first 5 examples
                    content += f"**`{issue['file']}:{issue['line']}`** - {issue['location']}\n"
                    content += f"- Problem: {issue['problem']}\n"
                    content += f"- Fix: {issue['fix']}\n"
                    content += f"- Impact: {issue['impact']}\n\n"
                if len(issues) > 5:
                    content += f"... and {len(issues) - 5} more samples with this issue\n\n"
        else:
            content += "✅ No blocking issues found! All code samples should run correctly.\n\n"

        content += "## 💡 Improvement Opportunities\n\nThese suggestions would make the documentation examples even better:\n\n"

        if improvement_suggestions:
            # Group by issue type
            suggestions_by_type = {}
            for suggestion in improvement_suggestions:
                suggestion_type = suggestion["issue"]
                if suggestion_type not in suggestions_by_type:
                    suggestions_by_type[suggestion_type] = []
                suggestions_by_type[suggestion_type].append(suggestion)

            for suggestion_type, suggestions in suggestions_by_type.items():
                content += f"### {suggestion_type} ({len(suggestions)} samples)\n\n"
                content += f"**Why this helps:** {suggestions[0]['impact']}\n\n"
                content += f"**How to fix:** {suggestions[0]['fix']}\n\n"
                content += f"**Examples:**\n"
                for suggestion in suggestions[:3]:
                    content += f"- `{suggestion['file']}:{suggestion['line']}`\n"
                if len(suggestions) > 3:
                    content += f"- ... and {len(suggestions) - 3} more samples\n"
                content += "\n"
        else:
            content += "✨ No improvement suggestions - your documentation examples are excellent!\n\n"

        # Create concrete next steps based on actual findings
        next_steps_content = "## Next Steps\n\n"

        if blocking_issues:
            next_steps_content += "### 🚨 Immediate Actions (Blocking Issues)\n"
            next_steps_content += "These must be fixed for users to run the code:\n\n"

            # Get unique issue types for action items
            blocking_types = list(set(issue["issue"] for issue in blocking_issues))
            for i, issue_type in enumerate(blocking_types[:5], 1):  # Top 5 types
                sample_count = len([issue for issue in blocking_issues if issue["issue"] == issue_type])
                next_steps_content += f"{i}. **Fix {issue_type}** in {sample_count} sample(s)\n"

        if improvement_suggestions:
            next_steps_content += "\n### 💡 Quality Improvements (Nice to Have)\n"
            next_steps_content += "These would make examples even better:\n\n"

            # Get unique suggestion types
            suggestion_types = list(set(suggestion["issue"] for suggestion in improvement_suggestions))
            for i, suggestion_type in enumerate(suggestion_types[:3], 1):  # Top 3 types
                sample_count = len([suggestion for suggestion in improvement_suggestions if suggestion["issue"] == suggestion_type])
                next_steps_content += f"{i}. **Implement {suggestion_type}** in {sample_count} sample(s)\n"

        if not blocking_issues and not improvement_suggestions:
            next_steps_content += "🎉 **No action needed!** All documentation samples are in excellent condition.\n\n"

        next_steps_content += f"\n---\n*Analysis completed - check individual sample details above for specific fixes.*\n\n"
        next_steps_content += "> 💡 **How to use this report**: Look at the specific file:line references above, make the suggested changes, then re-run analysis to verify fixes."

        content += next_steps_content

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

            total = report['summary']['total']
            passed = report['summary']['passed']
            failed = report['summary']['failed']

            print(f"✅ {language} analysis complete: {total} samples analyzed")

            # Calculate actual issue counts from the detailed results
            blocking_count = 0
            suggestion_count = 0

            for result in results:
                if "findings" in result.validation_results:
                    findings = result.validation_results["findings"]
                    blocking_count += len([f for f in findings if f.get("blocking", False)])
                    suggestion_count += len([f for f in findings if not f.get("blocking", False)])

            if blocking_count == 0:
                if suggestion_count == 0:
                    print("🎉 Perfect! All samples are ready to use with no issues found.")
                else:
                    print(f"✅ All samples work correctly. Found {suggestion_count} opportunities for improvement.")
            else:
                print(f"🚨 Found {blocking_count} issues that prevent code from running correctly.")
                if suggestion_count > 0:
                    print(f"💡 Also found {suggestion_count} suggestions to improve the examples.")

            print("📋 Check the detailed markdown report for specific fixes and improvements!")

        except Exception as e:
            print(f"❌ Failed to test {language}: {e}")
            overall_success = False

        print()

    if overall_success:
        print("🎉 Analysis complete - all documentation samples are excellent!")
        return 0
    else:
        print("📈 Analysis complete! Some samples have improvement opportunities.")
        print("💡 Check the detailed markdown reports for specific actionable suggestions.")
        return 0  # Return 0 since this is analysis, not testing


if __name__ == "__main__":
    sys.exit(main())
