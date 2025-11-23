#!/usr/bin/env python3
"""
Production Cleanup Script
Helps prepare the project for production deployment
"""

import os
import re
from pathlib import Path

def find_print_statements(directory):
    """Find all print() statements in Python files"""
    print("Searching for print() statements...\n")
    
    print_files = []
    for root, dirs, files in os.walk(directory):
        # Skip __pycache__ and venv directories
        dirs[:] = [d for d in dirs if d not in ['__pycache__', 'venv', '.venv', 'tests']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    try:
                        content = f.read()
                        # Find print statements
                        matches = re.finditer(r'print\s*\(', content)
                        count = len(list(matches))
                        if count > 0:
                            print_files.append((filepath, count))
                    except Exception as e:
                        print(f"ERROR reading {filepath}: {e}")
    
    if print_files:
        print(f"Found print() statements in {len(print_files)} files:\n")
        for filepath, count in sorted(print_files, key=lambda x: x[1], reverse=True):
            rel_path = os.path.relpath(filepath, directory)
            print(f"  {rel_path}: {count} print statements")
    else:
        print("OK: No print() statements found!")
    
    return print_files

def find_todos_fixmes(directory):
    """Find TODO and FIXME comments"""
    print("\nSearching for TODO/FIXME comments...\n")
    
    todo_files = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ['__pycache__', 'venv', '.venv', 'tests']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    try:
                        for line_num, line in enumerate(f, 1):
                            if 'TODO' in line or 'FIXME' in line:
                                todo_files.append((filepath, line_num, line.strip()))
                    except Exception as e:
                        print(f"ERROR reading {filepath}: {e}")
    
    if todo_files:
        print(f"Found {len(todo_files)} TODO/FIXME comments:\n")
        for filepath, line_num, line in todo_files:
            rel_path = os.path.relpath(filepath, directory)
            print(f"  {rel_path}:{line_num}")
            print(f"     {line}\n")
    else:
        print("OK: No TODO/FIXME comments found!")
    
    return todo_files

def check_env_file():
    """Check if .env file exists and has required variables"""
    print("\nChecking .env configuration...\n")
    
    required_vars = [
        'MONGODB_URL',
        'DATABASE_NAME',
        'TELEGRAM_BOT_TOKEN',
        'BOT_ADMIN_IDS',
        'PAYMENT_CHANNEL_ID',
        'NEWS_CHANNEL_USERNAME',
        'SUPPORT_USERNAME',
        'DEFAULT_SUBSCRIPTION_DOMAIN',
        'CARD_NUMBER',
        'GERMANY_PANEL_USERNAME',
        'GERMANY_PANEL_PASSWORD',
        'TURKEY_PANEL_USERNAME',
        'TURKEY_PANEL_PASSWORD',
    ]
    
    if not os.path.exists('.env'):
        print("ERROR: .env file not found!")
        print("   Copy .env.example to .env and configure it")
        return False
    
    with open('.env', 'r', encoding='utf-8') as f:
        env_content = f.read()
    
    missing_vars = []
    placeholder_vars = []
    
    for var in required_vars:
        if var not in env_content:
            missing_vars.append(var)
        else:
            # Check for placeholder values
            pattern = f"{var}=(.+)"
            match = re.search(pattern, env_content)
            if match:
                value = match.group(1).strip()
                if any(placeholder in value.lower() for placeholder in ['your_', 'password', 'admin', 'example', 'change']):
                    placeholder_vars.append(var)
    
    if missing_vars:
        print("ERROR: Missing environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
    
    if placeholder_vars:
        print("\nWARNING: Variables with placeholder values (need to be changed):")
        for var in placeholder_vars:
            print(f"   - {var}")
    
    if not missing_vars and not placeholder_vars:
        print("OK: All required environment variables are set!")
        return True
    
    return False

def check_secret_key():
    """Check if SECRET_KEY has been changed from default"""
    print("\nChecking SECRET_KEY...\n")
    
    config_path = 'app/core/config.py'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'your-secret-key-change-in-production' in content:
                print("ERROR: SECRET_KEY still has default value!")
                print("   Change it in app/core/config.py")
                return False
    
    print("OK: SECRET_KEY has been changed!")
    return True

def check_gitignore():
    """Check if sensitive files are in .gitignore"""
    print("\nChecking .gitignore...\n")
    
    required_entries = ['.env', '*.log', '__pycache__/', 'venv/', '.venv/']
    
    if not os.path.exists('.gitignore'):
        print("ERROR: .gitignore file not found!")
        return False
    
    with open('.gitignore', 'r', encoding='utf-8') as f:
        gitignore_content = f.read()
    
    missing_entries = [entry for entry in required_entries if entry not in gitignore_content]
    
    if missing_entries:
        print("WARNING: Missing entries in .gitignore:")
        for entry in missing_entries:
            print(f"   - {entry}")
        return False
    
    print("OK: .gitignore is properly configured!")
    return True

def check_panels_yaml():
    """Check panels.yaml configuration"""
    print("\nChecking panels.yaml...\n")
    
    panels_path = 'config/panels.yaml'
    if not os.path.exists(panels_path):
        print("ERROR: panels.yaml not found!")
        return False
    
    with open(panels_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # Check for placeholder IPs
    if '1.2.3.4' in content or '0.0.0.0' in content:
        issues.append("Contains placeholder IP addresses")
    
    # Check for enabled panels
    if 'enabled: true' not in content:
        issues.append("No panels are enabled")
    
    if issues:
        print("WARNING: Issues found in panels.yaml:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    
    print("OK: panels.yaml looks good!")
    return True

def check_migration_system():
    """Check if user migration system is implemented"""
    print("\nChecking user migration system...\n")
    
    migration_files = [
        'app/services/migration_service.py',
        'app/api/endpoints/migration.py',
        'scripts/migrate_users.py'
    ]
    
    missing_files = []
    for file_path in migration_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("WARNING: Migration system files missing:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        print("\n   Migration system allows transferring users between panels")
        print("   This is important for load balancing and maintenance")
        return False
    
    print("OK: User migration system is implemented!")
    return True

def generate_report():
    """Generate a comprehensive production readiness report"""
    print("=" * 60)
    print("VPN Bot Production Readiness Check")
    print("=" * 60)
    
    # Change to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    
    results = {
        'env_file': check_env_file(),
        'secret_key': check_secret_key(),
        'gitignore': check_gitignore(),
        'panels_yaml': check_panels_yaml(),
        'migration_system': check_migration_system(),
    }
    
    print_files = find_print_statements('app')
    todo_files = find_todos_fixmes('app')
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    print(f"\nPassed: {passed}/{total} checks")
    
    if print_files:
        print(f"WARNING: Found {len(print_files)} files with print() statements")
    
    if todo_files:
        print(f"WARNING: Found {len(todo_files)} TODO/FIXME comments")
    
    print("\n" + "=" * 60)
    
    if passed == total and not print_files and not todo_files:
        print("SUCCESS: Project is ready for production!")
    else:
        print("WARNING: Please address the issues above before deploying")
        print("\nRecommendations:")
        print("1. Replace all print() with proper logging")
        print("2. Resolve or remove TODO/FIXME comments")
        print("3. Configure all environment variables")
        print("4. Review PRODUCTION_CHECKLIST.md")
    
    print("=" * 60)

if __name__ == "__main__":
    generate_report()
