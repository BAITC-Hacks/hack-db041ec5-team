"""Build a source release without secrets, caches or private datasets."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root = Path(__file__).resolve().parents[1]
out = root / 'dist'
out.mkdir(exist_ok=True)
folders = ['moneygraph', 'ui', 'assistant', 'tests', 'tests_c', 'docs', 'scripts', '.streamlit', 'data/demo', 'output/demo']
files = [p for p in root.iterdir() if p.is_file() and (p.suffix in {'.py', '.md', '.txt', '.yaml', '.ps1'} or p.name in {'.gitignore', '.env.example'})]
for folder in folders:
    files.extend(p for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
with ZipFile(out / 'money-graph-dashboard.zip', 'w', ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, Path('money-graph') / path.relative_to(root))
print(out / 'money-graph-dashboard.zip')
