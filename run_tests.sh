#!/bin/bash
# Run Moonstone test suite
# Usage: ./run_tests.sh [options]
#   --verbose        Run with verbose output
#   --coverage       Run with coverage report
#   --watch          Watch mode (re-run on file changes)
#   --concurrency    Run only concurrency tests
#   --fast           Skip slow tests
#   --help           Show this message

set -e

# Default options (use array for proper argument handling)
PYTEST_ARGS=("-v")
TEST_PATH=("tests/")

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --verbose)
      PYTEST_ARGS=("-vv" "-s")
      shift
      ;;
    --coverage)
      PYTEST_ARGS+=("--cov=moonstone" "--cov-report=term-missing" "--cov-report=html")
      shift
      ;;
    --watch)
      PYTEST_ARGS+=("-f")
      shift
      ;;
    --concurrency)
      TEST_PATH=("-m" "concurrency")
      shift
      ;;
    --fast)
      PYTEST_ARGS+=("-m" "not slow")
      shift
      ;;
    --help)
      echo "Usage: ./run_tests.sh [options]"
      echo ""
      echo "Options:"
      echo "  --verbose        Run with verbose output (-vv -s)"
      echo "  --coverage       Run with coverage report"
      echo "  --watch          Watch mode (re-run on file changes)"
      echo "  --concurrency    Run only concurrency tests"
      echo "  --fast           Skip slow tests"
      echo "  --help           Show this message"
      echo ""
      echo "Examples:"
      echo "  ./run_tests.sh                # Run all tests"
      echo "  ./run_tests.sh --verbose      # Verbose output"
      echo "  ./run_tests.sh --coverage     # With coverage report"
      echo "  ./run_tests.sh --concurrency  # Only concurrency tests"
      echo "  ./run_tests.sh --fast         # Skip slow tests"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run --help for usage"
      exit 1
      ;;
  esac
done

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
  echo "Error: pytest not found. Install it with:"
  echo "  pip install pytest"
  exit 1
fi

# Run tests
echo "Running tests with: pytest ${PYTEST_ARGS[*]} ${TEST_PATH[*]}"
echo ""
python -m pytest "${PYTEST_ARGS[@]}" "${TEST_PATH[@]}"

# Exit with pytest's exit code
exit $?
