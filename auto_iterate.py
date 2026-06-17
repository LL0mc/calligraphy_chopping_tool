"""Auto-iterate: run pipeline on submitted pages and evaluate"""
import sys, os, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output', 'pages')

def get_reviewed_pages():
    pages = set()
    for f in os.listdir(PAGE_DIR):
        if f.endswith('_reviewed.json'):
            pages.add(int(f.split('_')[1]))
    return sorted(pages)

def backup_results():
    import shutil
    for f in os.listdir(PAGE_DIR):
        if f.endswith('_ocr_results.json'):
            src = os.path.join(PAGE_DIR, f)
            dst = src + '.bak'
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

def run_iteration(iteration_name):
    pages = get_reviewed_pages()
    print(f"\n{'='*60}")
    print(f"ITERATION: {iteration_name}")
    print(f"Pages: {pages}")
    print(f"{'='*60}")
    
    for p in pages:
        print(f"\n--- Page {p} ---")
        result = subprocess.run(
            [sys.executable, 'pipeline.py', str(p), '--no-correct'],
            capture_output=True, timeout=120
        )
        stdout = result.stdout.decode('utf-8', errors='replace')
        stderr = result.stderr.decode('utf-8', errors='replace')
        print(stdout[-500:] if len(stdout) > 500 else stdout)
        if stderr.strip():
            print(f"STDERR: {stderr[-300:]}")
    
    print(f"\n--- Evaluating {iteration_name} ---")
    result = subprocess.run(
        [sys.executable, 'src/evaluator.py'],
        capture_output=True, timeout=60
    )
    output = result.stdout.decode('utf-8', errors='replace')
    print(output)
    stderr = result.stderr.decode('utf-8', errors='replace')
    if stderr.strip():
        print(f"STDERR: {stderr[-300:]}")
    
    # Extract summary
    lines = output.split('\n')
    summary_lines = []
    in_summary = False
    for line in lines:
        if 'BASELINE EVALUATION SUMMARY' in line:
            in_summary = True
        if in_summary:
            summary_lines.append(line)
    
    return '\n'.join(summary_lines)

if __name__ == '__main__':
    iteration = sys.argv[1] if len(sys.argv) > 1 else 'iter_1'
    run_iteration(iteration)
