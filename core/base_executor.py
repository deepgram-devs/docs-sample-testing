#!/usr/bin/env python3
"""
Base Executor - Abstract interface for language-specific test execution
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class CodeSample:
    """Universal code sample representation"""
    file_path: str
    line_number: int
    code: str
    language: str
    sample_type: str  # "sync", "async", "streaming", etc.
    imports: List[str]
    requires_api_key: bool
    requires_audio_file: bool
    metadata: Dict[str, Any]


@dataclass
class TestResult:
    """Universal test result representation"""
    sample: CodeSample
    success: bool
    execution_time: float
    stdout: str = ""
    stderr: str = ""
    error_message: str = ""
    validation_results: Dict[str, bool] = None

    def __post_init__(self):
        if self.validation_results is None:
            self.validation_results = {}


class BaseExecutor(ABC):
    """
    Abstract base class for language-specific test executors.

    Each language (Python, JavaScript, Go, etc.) implements this interface
    to provide consistent testing capabilities across all SDKs.
    """

    def __init__(self, language_config: Dict[str, Any], framework_config: Dict[str, Any]):
        self.language_config = language_config
        self.framework_config = framework_config
        self.language_name = language_config['language']['name']

    @abstractmethod
    def extract_samples(self, documentation_path: Path) -> List[CodeSample]:
        """
        Extract code samples from documentation files.

        Args:
            documentation_path: Path to documentation directory

        Returns:
            List of extracted code samples
        """
        pass

    @abstractmethod
    def validate_sample(self, sample: CodeSample) -> Dict[str, bool]:
        """
        Validate a code sample against current SDK patterns.

        Args:
            sample: Code sample to validate

        Returns:
            Dictionary of validation results {rule_name: passed}
        """
        pass

    @abstractmethod
    def prepare_test_environment(self, sample: CodeSample) -> Dict[str, Any]:
        """
        Prepare the environment for testing a code sample.
        This might include setting up dependencies, mock data, etc.

        Args:
            sample: Code sample to prepare for

        Returns:
            Dictionary with environment setup information
        """
        pass

    @abstractmethod
    def execute_sample(self, sample: CodeSample, environment: Dict[str, Any]) -> TestResult:
        """
        Execute a code sample and return the results.

        Args:
            sample: Code sample to execute
            environment: Environment setup from prepare_test_environment

        Returns:
            Test result with success/failure and output
        """
        pass

    @abstractmethod
    def cleanup_test_environment(self, environment: Dict[str, Any]) -> None:
        """
        Clean up after test execution.

        Args:
            environment: Environment setup to clean up
        """
        pass

    # Common helper methods that can be overridden if needed

    def get_sample_priority(self, sample: CodeSample) -> str:
        """Determine the priority level of a code sample"""
        priority_levels = self.framework_config.get('priority_levels', {})

        # Check sample type against priority configuration
        for priority, patterns in priority_levels.items():
            if sample.sample_type in patterns:
                return priority

        return "medium"  # default

    def should_skip_sample(self, sample: CodeSample) -> bool:
        """Determine if a sample should be skipped"""
        # Skip very short samples or comment-only samples
        if len(sample.code.strip()) < 20:
            return True

        # Skip if it's just comments
        lines = [line.strip() for line in sample.code.split('\n') if line.strip()]
        if all(line.startswith('#') for line in lines):
            return True

        return False

    def get_validation_rules(self) -> List[Dict[str, Any]]:
        """Get validation rules for this language"""
        return self.language_config.get('validation_rules', [])

    def create_mock_environment(self) -> Dict[str, str]:
        """Create mock environment variables for testing"""
        env = {}

        # Add mock API key
        api_key = self.framework_config.get('mocking', {}).get('api_key_placeholder', 'test_key')
        env['DEEPGRAM_API_KEY'] = api_key
        env['DEEPGRAM_TOKEN'] = api_key

        return env
