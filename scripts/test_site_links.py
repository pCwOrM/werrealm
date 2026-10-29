import re
import os

docs_dir = r"c:\Users\maat\Documents\antigravity\wonderful-raman\werrealm\docs"
html_files = [f for f in os.listdir(docs_dir) if f.endswith(".html")]

print("=== HTML FILES LINK AND SYNTAX INTEGRITY TEST ===")
for hf in html_files:
    path = os.path.join(docs_dir, hf)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check title, meta viewport
    has_viewport = 'name="viewport"' in content
    has_title = '<title>' in content
    
    # Find all internal links href="..."
    hrefs = re.findall(r'href="([^"]+)"', content)
    internal_links = [h for h in hrefs if not h.startswith("http") and not h.startswith("#") and not h.startswith("mailto:")]
    
    print(f"\n[*] File: {hf}")
    print(f"    - Viewport meta: {'OK' if has_viewport else 'MISSING'}")
    print(f"    - Title tag    : {'OK' if has_title else 'MISSING'}")
    print(f"    - Internal hrefs: {internal_links}")
    
    for il in internal_links:
        # resolve target
        clean_il = il.lstrip("/")
        target_path = os.path.join(docs_dir, clean_il if clean_il else "index.html")
        exists = os.path.exists(target_path)
        print(f"      -> Link '{il}' exists? {'YES' if exists else 'BROKEN!'}")

print("\n=== TEST COMPLETED ===")
