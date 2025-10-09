package main

// Go SDK Test Executor
// Example implementation showing how Go SDK testing would integrate

import (
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// GoExecutor implements SDK testing for Go samples
type GoExecutor struct {
	LanguageConfig  map[string]interface{}
	FrameworkConfig map[string]interface{}
	SDKPath         string
}

// CodeSample represents a Go code sample extracted from documentation
type CodeSample struct {
	FilePath          string            `json:"file_path"`
	LineNumber        int               `json:"line_number"`
	Code              string            `json:"code"`
	Language          string            `json:"language"`
	SampleType        string            `json:"sample_type"`
	Imports           []string          `json:"imports"`
	RequiresAPIKey    bool              `json:"requires_api_key"`
	RequiresAudioFile bool              `json:"requires_audio_file"`
	Metadata          map[string]string `json:"metadata"`
}

// TestResult represents the result of testing a Go sample
type TestResult struct {
	Sample            CodeSample      `json:"sample"`
	Success           bool            `json:"success"`
	ExecutionTime     float64         `json:"execution_time"`
	Stdout            string          `json:"stdout"`
	Stderr            string          `json:"stderr"`
	ErrorMessage      string          `json:"error_message"`
	ValidationResults map[string]bool `json:"validation_results"`
}

// NewGoExecutor creates a new Go executor
func NewGoExecutor(langConfig, frameworkConfig map[string]interface{}) *GoExecutor {
	sdkConfig := langConfig["sdk"].(map[string]interface{})
	repoPath := sdkConfig["repository_path"].(string)
	sourcePath := sdkConfig["source_path"].(string)

	return &GoExecutor{
		LanguageConfig:  langConfig,
		FrameworkConfig: frameworkConfig,
		SDKPath:         filepath.Join(repoPath, sourcePath),
	}
}

// ExtractSamples finds and extracts Go code samples from documentation
func (e *GoExecutor) ExtractSamples(documentationPath string) ([]CodeSample, error) {
	var samples []CodeSample

	pagesPath := filepath.Join(documentationPath, "fern", "pages")

	err := filepath.WalkDir(pagesPath, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}

		if !strings.HasSuffix(path, ".mdx") {
			return nil
		}

		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}

		fileSamples := e.extractGoSamplesFromContent(path, string(content))
		samples = append(samples, fileSamples...)

		return nil
	})

	return samples, err
}

func (e *GoExecutor) extractGoSamplesFromContent(filePath, content string) []CodeSample {
	var samples []CodeSample

	// Regex to find Go code blocks
	codeBlockRegex := regexp.MustCompile("```go[^\n]*\n(.*?)```")
	matches := codeBlockRegex.FindAllStringSubmatch(content, -1)

	for _, match := range matches {
		if len(match) < 2 {
			continue
		}

		code := strings.TrimSpace(match[1])

		// Skip if too short or not Go SDK related
		if len(code) < 30 || !strings.Contains(code, "deepgram") {
			continue
		}

		// Calculate line number (simplified)
		lineNumber := strings.Count(content[:strings.Index(content, match[0])], "\n") + 1

		sample := CodeSample{
			FilePath:          filePath,
			LineNumber:        lineNumber,
			Code:              code,
			Language:          "go",
			SampleType:        e.determineSampleType(code),
			Imports:           e.extractImports(code),
			RequiresAPIKey:    e.requiresAPIKey(code),
			RequiresAudioFile: e.requiresAudioFile(code),
			Metadata:          make(map[string]string),
		}

		samples = append(samples, sample)
	}

	return samples
}

func (e *GoExecutor) determineSampleType(code string) string {
	if strings.Contains(code, "goroutine") || strings.Contains(code, "go func") {
		return "concurrent"
	}
	if strings.Contains(code, "type") && strings.Contains(code, "struct") {
		return "struct"
	}
	return "simple"
}

func (e *GoExecutor) extractImports(code string) []string {
	importRegex := regexp.MustCompile(`import\s+(?:\(\s*((?:[^\)]+\n?)+)\s*\)|"([^"]+)")`)
	matches := importRegex.FindAllStringSubmatch(code, -1)

	var imports []string
	for _, match := range matches {
		if len(match) > 2 && match[2] != "" {
			imports = append(imports, match[2])
		}
	}

	return imports
}

func (e *GoExecutor) requiresAPIKey(code string) bool {
	patterns := []string{"api_key", "DEEPGRAM_API_KEY", "client.New"}
	for _, pattern := range patterns {
		if strings.Contains(code, pattern) {
			return true
		}
	}
	return false
}

func (e *GoExecutor) requiresAudioFile(code string) bool {
	patterns := []string{".wav", ".mp3", "audio_file", "transcribe"}
	for _, pattern := range patterns {
		if strings.Contains(strings.ToLower(code), strings.ToLower(pattern)) {
			return true
		}
	}
	return false
}

// ValidateSample checks Go sample against current SDK patterns
func (e *GoExecutor) ValidateSample(sample CodeSample) map[string]bool {
	results := make(map[string]bool)

	// Example validation: check for v2 import paths
	if strings.Contains(sample.Code, "deepgram-go-sdk/v2") {
		results["uses_v2_imports"] = true
	} else {
		results["uses_v2_imports"] = false
	}

	// Check for deprecated patterns
	if strings.Contains(sample.Code, "deepgram.New") {
		results["no_old_client"] = false
	} else {
		results["no_old_client"] = true
	}

	return results
}

// ExecuteSample runs a Go code sample and returns the result
func (e *GoExecutor) ExecuteSample(sample CodeSample) TestResult {
	startTime := time.Now()

	// Create temporary directory for test
	tempDir, err := os.MkdirTemp("", "go-test-*")
	if err != nil {
		return TestResult{
			Sample:       sample,
			Success:      false,
			ErrorMessage: err.Error(),
		}
	}
	defer os.RemoveAll(tempDir)

	// Create test Go file
	testFile := filepath.Join(tempDir, "main.go")
	testCode := e.prepareCodeForExecution(sample)

	err = os.WriteFile(testFile, []byte(testCode), 0644)
	if err != nil {
		return TestResult{
			Sample:       sample,
			Success:      false,
			ErrorMessage: err.Error(),
		}
	}

	// Initialize Go module
	cmd := exec.Command("go", "mod", "init", "test")
	cmd.Dir = tempDir
	cmd.Run() // Ignore errors for this example

	// Try to run the code
	cmd = exec.Command("go", "run", "main.go")
	cmd.Dir = tempDir
	cmd.Env = append(os.Environ(), "DEEPGRAM_API_KEY=test_key")

	output, err := cmd.CombinedOutput()
	executionTime := time.Since(startTime).Seconds()

	success := err == nil
	stderr := ""
	stdout := string(output)

	if err != nil {
		stderr = err.Error()
	}

	return TestResult{
		Sample:            sample,
		Success:           success,
		ExecutionTime:     executionTime,
		Stdout:            stdout,
		Stderr:            stderr,
		ValidationResults: e.ValidateSample(sample),
	}
}

func (e *GoExecutor) prepareCodeForExecution(sample CodeSample) string {
	code := sample.Code

	// Add package declaration if missing
	if !strings.HasPrefix(code, "package") {
		code = "package main\n\n" + code
	}

	// Replace placeholder API keys
	code = strings.ReplaceAll(code, `"YOUR_API_KEY"`, `"test_key"`)

	// Add basic error handling for network calls
	if strings.Contains(code, "http://") || strings.Contains(code, "https://") {
		code = "// Note: This would make real network calls\n" + code
	}

	return code
}

// CLI interface for integration with Python test runner
func main() {
	if len(os.Args) < 2 {
		fmt.Println("Go executor ready")
		return
	}

	command := os.Args[1]
	fmt.Printf("Go executor: %s\n", command)

	// This would handle JSON communication with Python test runner
	// For example, reading config and samples from stdin,
	// returning results as JSON to stdout
}
