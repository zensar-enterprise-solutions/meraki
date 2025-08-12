# Makefile for Tesco AWS Infrastructure
# Common operations for security scanning and validation

.PHONY: help scan scan-fast scan-verbose validate clean install setup

# Default target
help: ## Show this help message
	@echo "🔒 Tesco AWS Infrastructure - Available Commands"
	@echo "================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Security scanning targets
scan: ## Run full KICS security scan
	@echo "🔍 Running KICS security scan..."
	@if [ -f "./scripts/run-kics-scan.ps1" ]; then \
		powershell -ExecutionPolicy Bypass -File "./scripts/run-kics-scan.ps1"; \
	elif [ -f "./scripts/run-kics-scan.sh" ]; then \
		chmod +x ./scripts/run-kics-scan.sh && ./scripts/run-kics-scan.sh; \
	else \
		echo "❌ KICS scan script not found"; \
	fi

scan-fast: ## Run KICS scan with minimal output
	@echo "⚡ Running fast KICS security scan..."
	@if [ -f "./scripts/run-kics-scan.sh" ]; then \
		./scripts/run-kics-scan.sh --formats json,cli; \
	else \
		powershell -ExecutionPolicy Bypass -File "./scripts/run-kics-scan.ps1" -OutputFormats @("json","cli"); \
	fi

scan-verbose: ## Run KICS scan with detailed output
	@echo "📋 Running verbose KICS security scan..."
	@if [ -f "./scripts/run-kics-scan.sh" ]; then \
		./scripts/run-kics-scan.sh --formats json,html,sarif,cli; \
	else \
		powershell -ExecutionPolicy Bypass -File "./scripts/run-kics-scan.ps1" -OutputFormats @("json","html","sarif","cli"); \
	fi

scan-production: ## Scan only production CloudFormation templates
	@echo "🏭 Scanning production templates..."
	@if [ -f "./scripts/run-kics-scan.sh" ]; then \
		./scripts/run-kics-scan.sh --path cloudformation/production; \
	else \
		powershell -ExecutionPolicy Bypass -File "./scripts/run-kics-scan.ps1" -Path "cloudformation/production"; \
	fi

scan-sandbox: ## Scan only sandbox CloudFormation templates
	@echo "🧪 Scanning sandbox templates..."
	@if [ -f "./scripts/run-kics-scan.sh" ]; then \
		./scripts/run-kics-scan.sh --path cloudformation/sandbox; \
	else \
		powershell -ExecutionPolicy Bypass -File "./scripts/run-kics-scan.ps1" -Path "cloudformation/sandbox"; \
	fi

# Validation targets
validate: ## Validate all CloudFormation templates
	@echo "✅ Validating CloudFormation templates..."
	@find cloudformation -name "*.yml" -o -name "*.yaml" | while read template; do \
		echo "Validating $$template..."; \
		aws cloudformation validate-template --template-body file://$$template > /dev/null && \
		echo "✅ $$template is valid" || echo "❌ $$template is invalid"; \
	done

validate-production: ## Validate production CloudFormation templates
	@echo "✅ Validating production CloudFormation templates..."
	@find cloudformation/production -name "*.yml" -o -name "*.yaml" | while read template; do \
		echo "Validating $$template..."; \
		aws cloudformation validate-template --template-body file://$$template > /dev/null && \
		echo "✅ $$template is valid" || echo "❌ $$template is invalid"; \
	done

# Setup and maintenance targets
setup: ## Set up local development environment
	@echo "🛠️  Setting up local development environment..."
	@echo "Creating directories..."
	@mkdir -p tools kics-results
	@echo "Setting up git hooks..."
	@if [ -f ".githooks/pre-commit" ]; then \
		cp .githooks/pre-commit .git/hooks/pre-commit; \
		chmod +x .git/hooks/pre-commit; \
		echo "✅ Pre-commit hook installed"; \
	fi
	@echo "✅ Setup complete"

install: ## Install KICS scanner
	@echo "📥 Installing KICS scanner..."
	@if [ -f "./scripts/run-kics-scan.sh" ]; then \
		./scripts/run-kics-scan.sh --skip-download false; \
	else \
		powershell -ExecutionPolicy Bypass -File "./scripts/run-kics-scan.ps1"; \
	fi

clean: ## Clean up scan results and temporary files
	@echo "🧹 Cleaning up..."
	@rm -rf kics-results/
	@rm -rf tools/kics/
	@rm -f *.log
	@echo "✅ Cleanup complete"

# Git and development targets
pre-commit: ## Run pre-commit checks (security scan + validation)
	@echo "🔒 Running pre-commit checks..."
	@$(MAKE) scan-fast
	@$(MAKE) validate

status: ## Show repository and scan status
	@echo "📊 Repository Status"
	@echo "==================="
	@echo "Git branch: $$(git branch --show-current 2>/dev/null || echo 'unknown')"
	@echo "Git status:"
	@git status --porcelain || echo "Not a git repository"
	@echo ""
	@echo "CloudFormation templates:"
	@find cloudformation -name "*.yml" -o -name "*.yaml" | wc -l | sed 's/^/  Total: /'
	@echo ""
	@echo "Last scan results:"
	@if [ -f "kics-results/results.json" ]; then \
		echo "  Available in: kics-results/"; \
		if command -v jq >/dev/null 2>&1; then \
			echo "  Files scanned: $$(jq -r '.files_scanned // "N/A"' kics-results/results.json)"; \
			echo "  High issues: $$(jq -r '.severity_counters.HIGH // 0' kics-results/results.json)"; \
			echo "  Medium issues: $$(jq -r '.severity_counters.MEDIUM // 0' kics-results/results.json)"; \
		fi \
	else \
		echo "  No recent scan results found"; \
	fi

# Development workflow targets
dev-workflow: ## Complete development workflow (scan, validate, commit)
	@echo "🚀 Running complete development workflow..."
	@$(MAKE) scan
	@$(MAKE) validate
	@echo "✅ Development workflow complete"

ci-check: ## Run CI-like checks locally
	@echo "🤖 Running CI checks locally..."
	@$(MAKE) scan-verbose
	@$(MAKE) validate
	@echo "✅ CI checks complete"

# Documentation targets
docs: ## Open security scanning documentation
	@echo "📖 Opening KICS security scanning documentation..."
	@if [ -f "docs/KICS-SECURITY-SCANNING.md" ]; then \
		if command -v code >/dev/null 2>&1; then \
			code docs/KICS-SECURITY-SCANNING.md; \
		elif command -v open >/dev/null 2>&1; then \
			open docs/KICS-SECURITY-SCANNING.md; \
		else \
			echo "Please open docs/KICS-SECURITY-SCANNING.md manually"; \
		fi \
	else \
		echo "❌ Documentation not found"; \
	fi

report: ## Open latest HTML security report
	@echo "📊 Opening latest security report..."
	@if [ -f "kics-results/results.html" ]; then \
		if command -v open >/dev/null 2>&1; then \
			open kics-results/results.html; \
		elif command -v start >/dev/null 2>&1; then \
			start kics-results/results.html; \
		else \
			echo "Please open kics-results/results.html manually"; \
		fi \
	else \
		echo "❌ No HTML report found. Run 'make scan' first"; \
	fi
