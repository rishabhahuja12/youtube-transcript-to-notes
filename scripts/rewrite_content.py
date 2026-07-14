import os, sys, re

path = "gateway/content_service.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Imports
content = content.replace("import tempfile\nimport urllib.request", "import tempfile\nimport urllib.request\nimport uuid\nfrom pathlib import Path")

# 2. CourseInfo
old_course_info = """class CourseInfo(BaseModel):
    \"\"\"Summary info for a single course in the library.\"\"\"
    title: str
    path: str
    date: str
    badges: CourseBadges"""
new_course_info = """class CourseInfo(BaseModel):
    \"\"\"Summary info for a single course in the library.\"\"\"
    id: str
    title: str
    path: str
    date: str
    badges: CourseBadges
    status: str = "complete\""""
content = content.replace(old_course_info, new_course_info)

# 3. Replace _load_recent_outputs, _add_recent_output, _resolve_course_dir
old_funcs_start = content.find("def _load_recent_outputs() -> List[str]:")
end_resolve = content.find("def _check_ollama() -> bool:")

new_funcs = """def _load_library_entries() -> List[Dict[str, Any]]:
    \"\"\"Load the list of library entries.

    Returns:
        List of entry dictionaries from config.json.
    \"\"\"
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            entries = data.get("library", [])
            # Migrate legacy recent_outputs if library is empty
            if not entries and "recent_outputs" in data:
                legacy = data["recent_outputs"]
                for p in legacy:
                    entries.append({
                        "id": uuid.uuid4().hex,
                        "path": p,
                        "title": os.path.basename(p) or p,
                        "status": "complete"
                    })
            return entries
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _add_library_entry(path: str, title: str = "") -> Dict[str, Any]:
    \"\"\"Add an output directory path to the library.

    Args:
        path: The directory path to store.
        title: Optional title.
    Returns:
        The new library entry dictionary.
    \"\"\"
    if not path:
        return {}
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return {}
        
    entries = _load_library_entries()
    
    # Remove existing entry with same path
    entries = [e for e in entries if e.get("path") != path]
    
    entry_id = uuid.uuid4().hex
    if not title:
        title = os.path.basename(path) or path
        
    new_entry = {
        "id": entry_id,
        "path": path,
        "title": title,
        "status": "complete",
        "badges": {}
    }
    entries.insert(0, new_entry)
    
    try:
        data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        
        data["library"] = entries
        
        # Atomic write
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(CONFIG_PATH), text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp_path, CONFIG_PATH)
    except OSError as e:
        logging.error(f"Error saving library: {e}")
        
    return new_entry


def _resolve_course_dir(course_id: str) -> str:
    \"\"\"Resolve a course UUID to a validated directory path.

    Args:
        course_id: UUID string.

    Returns:
        Absolute directory path for the course.

    Raises:
        HTTPException: If not found.
    \"\"\"
    entries = _load_library_entries()
    for entry in entries:
        if str(entry.get("id")) == str(course_id):
            course_dir = entry.get("path")
            if not os.path.isdir(course_dir):
                raise HTTPException(status_code=404, detail="Course directory does not exist.")
            return course_dir
    raise HTTPException(status_code=404, detail=f"Invalid course_id: {course_id}")


"""
content = content[:old_funcs_start] + new_funcs + content[end_resolve:]

# 4. Modify endpoints taking id: int -> id: str
content = content.replace("async def get_course_files(id: int)", "async def get_course_files(id: str)")
content = content.replace("def get_course_files(id: int)", "def get_course_files(id: str)")

content = content.replace("async def get_course_notes(id: int, file: str)", "async def get_course_notes(id: str, file: str)")
content = content.replace("async def get_course_graph(id: int)", "async def get_course_graph(id: str)")
content = content.replace("async def get_course_keyframes(id: int)", "async def get_course_keyframes(id: str)")
content = content.replace("async def serve_static_file(id: int, filename: str)", "async def serve_static_file(id: str, filename: str)")
content = content.replace("class PdfExportRequest(BaseModel):\n    \"\"\"Request body for exporting markdown to PDF.\"\"\"\n    course_id: int", "class PdfExportRequest(BaseModel):\n    \"\"\"Request body for exporting markdown to PDF.\"\"\"\n    course_id: str")

# 5. Fix Path Traversal
# In get_course_notes
old_notes_logic = '''    safe_name = os.path.basename(file)
    if safe_name != file or ".." in file:
        logging.error(f"Invalid filename requested: {file}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
    if not safe_name.endswith(".md"):
        logging.error(f"Non-markdown file requested: {safe_name}")
        raise HTTPException(status_code=400, detail="Only .md files can be read.")

    filepath = os.path.join(course_dir, safe_name)'''
new_notes_logic = '''    course_root = Path(course_dir).resolve()
    try:
        requested_path = (course_root / file).resolve()
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    if not str(requested_path).startswith(str(course_root)):
        logging.error(f"Path traversal blocked: {file}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    if not requested_path.name.endswith(".md"):
        logging.error(f"Non-markdown file requested: {requested_path.name}")
        raise HTTPException(status_code=400, detail="Only .md files can be read.")
        
    filepath = str(requested_path)'''
content = content.replace(old_notes_logic, new_notes_logic)

# In serve_static_file
old_static_logic = '''    safe_name = os.path.basename(filename)
    if safe_name != filename or ".." in filename:
        logging.error(f"Invalid static filename requested: {filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")

    filepath = os.path.join(course_dir, safe_name)'''
new_static_logic = '''    course_root = Path(course_dir).resolve()
    try:
        requested_path = (course_root / filename).resolve()
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    if not str(requested_path).startswith(str(course_root)):
        logging.error(f"Path traversal blocked: {filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    filepath = str(requested_path)'''
content = content.replace(old_static_logic, new_static_logic)

# In pdf_export
old_pdf_logic = '''    safe_name = os.path.basename(req.filename)
    if safe_name != req.filename or ".." in req.filename:
        logging.error(f"Invalid PDF export filename requested: {req.filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
    if not safe_name.endswith(".md"):
        logging.error(f"Non-markdown file requested for PDF export: {safe_name}")
        raise HTTPException(status_code=400, detail="Only .md files can be exported.")

    md_path = os.path.join(course_dir, safe_name)'''
new_pdf_logic = '''    course_root = Path(course_dir).resolve()
    try:
        requested_path = (course_root / req.filename).resolve()
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    if not str(requested_path).startswith(str(course_root)):
        logging.error(f"Path traversal blocked for PDF: {req.filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    if not requested_path.name.endswith(".md"):
        logging.error(f"Non-markdown file requested for PDF export: {requested_path.name}")
        raise HTTPException(status_code=400, detail="Only .md files can be exported.")
        
    md_path = str(requested_path)'''
content = content.replace(old_pdf_logic, new_pdf_logic)

# get_library implementation
old_get_library = '''    outputs = _load_recent_outputs()
    courses: List[CourseInfo] = []
    for path in outputs:
        title = os.path.basename(path) or path
        date = ""
        try:
            stat = os.stat(path)
            from datetime import datetime
            date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        except OSError:
            date = "Unknown"
        badges = _detect_badges(path)
        courses.append(CourseInfo(title=title, path=path, date=date, badges=badges))
    return courses'''

new_get_library = '''    entries = _load_library_entries()
    courses: List[CourseInfo] = []
    for entry in entries:
        path = entry.get("path", "")
        title = entry.get("title", os.path.basename(path) or path)
        date = ""
        try:
            stat = os.stat(path)
            from datetime import datetime
            date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        except OSError:
            date = "Unknown"
        badges = _detect_badges(path)
        courses.append(CourseInfo(
            id=entry.get("id"),
            title=title,
            path=path,
            date=date,
            badges=badges,
            status=entry.get("status", "complete")
        ))
    return courses'''

content = content.replace(old_get_library, new_get_library)

# add_library_entry implementation
old_add_lib = '''@app.post("/content/library/add")
async def add_library_entry(req: LibraryAddRequest) -> Dict[str, bool]:
    \"\"\"Add a directory path to the library's recent outputs.
    
    Args:
        req: Request containing the path.
        
    Returns:
        Dict[str, bool]: Success status.
    \"\"\"
    _add_recent_output(req.path)
    return {"success": True}'''

new_add_lib = '''@app.post("/content/library/add")
async def add_library_entry(req: LibraryAddRequest) -> Dict[str, Any]:
    \"\"\"Add a directory path to the library's recent outputs.
    
    Args:
        req: Request containing the path.
        
    Returns:
        Dict[str, Any]: The added entry.
    \"\"\"
    entry = _add_library_entry(req.path)
    return entry'''

content = content.replace(old_add_lib, new_add_lib)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
