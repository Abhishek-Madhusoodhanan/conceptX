"""
All utility functions in ONE file
"""
import os
import json
import numpy as np
from pypdf import PdfReader
from docx import Document
import tempfile
import time

try:
    import faiss
    from sentence_transformers import SentenceTransformer
    VECTOR_ENABLED = True
except ImportError:
    VECTOR_ENABLED = False
    print("⚠️ Install: pip install faiss-cpu sentence-transformers")


# ========== AUDIO TRANSCRIPTION (Gemini) ==========
def process_audio_with_gemini(audio_file):
    """
    Transcribe audio using Gemini API with File API v1.0 (best-effort)
    Supports: MP3, WAV, M4A, FLAC, AAC, OGG
    """
    temp_file = None

    try:
        try:
            import google.generativeai as genai
        except Exception:
            return "Gemini SDK not installed. pip install google-generativeai"

        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return "Missing GOOGLE_API_KEY"
        try:
            genai.configure(api_key=api_key)
        except Exception:
            pass

        # Initialize a model name that is likely available; can be adjusted per account
        try:
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
        except Exception:
            model = genai.GenerativeModel('gemini-1.5-pro')

        # Step 1: Validate audio file BEFORE processing
        file_extension = os.path.splitext(audio_file.name)[1].lower()
        allowed_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg']
        if file_extension not in allowed_extensions:
            raise ValueError(f"Unsupported audio format: {file_extension}. Supported: {', '.join(allowed_extensions)}")
        if getattr(audio_file, 'size', None) is not None and audio_file.size == 0:
            raise ValueError("Audio file is empty")
        if getattr(audio_file, 'size', 0) > 25 * 1024 * 1024:
            raise ValueError(f"Audio file too large: {audio_file.size / 1024 / 1024:.1f}MB. Maximum: 25MB")

        # Step 2: Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension, prefix='audio_')
        # Django InMemoryUploadedFile has chunks
        if hasattr(audio_file, 'chunks'):
            for chunk in audio_file.chunks(chunk_size=8192):
                temp_file.write(chunk)
        else:
            temp_file.write(audio_file.read())
        temp_file.close()

        # Step 3: MIME type mapping
        mime_type_map = {
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.m4a': 'audio/mp4',
            '.flac': 'audio/flac',
            '.aac': 'audio/aac',
            '.ogg': 'audio/ogg'
        }
        mime_type = mime_type_map.get(file_extension, 'audio/mpeg')

        # Step 4: Upload file (best-effort)
        uploaded_file = None
        try:
            uploaded_file = genai.upload_file(path=temp_file.name, mime_type=mime_type)
        except Exception:
            uploaded_file = None

        # Step 5: Wait for processing if uploaded
        if uploaded_file is not None and hasattr(uploaded_file, 'state'):
            max_wait = 120
            start_time = time.time()
            check_interval = 2
            while getattr(uploaded_file, 'state', None) and getattr(uploaded_file.state, 'name', '') == 'PROCESSING':
                if time.time() - start_time > max_wait:
                    raise TimeoutError(f"Audio processing timeout after {max_wait}s")
                time.sleep(check_interval)
                try:
                    uploaded_file = genai.get_file(uploaded_file.name)
                except Exception:
                    break

        # Step 6: Generate transcription
        transcription_prompt = (
            "Transcribe this audio file with high accuracy.\n\n"
            "INSTRUCTIONS:\n"
            "1. Convert all speech to text exactly as spoken\n"
            "2. Include all details, numbers, and context mentioned\n"
            "3. Preserve technical terms and proper nouns\n"
            "4. Add natural punctuation and paragraph breaks\n"
            "5. If speaker mentions specific items or points, format them as bullet points\n\n"
            "TRANSCRIPTION:"
        )

        try:
            if uploaded_file is not None:
                response = model.generate_content([transcription_prompt, uploaded_file])
            else:
                with open(temp_file.name, 'rb') as f:
                    audio_bytes = f.read()
                response = model.generate_content([
                    transcription_prompt,
                    {"mime_type": mime_type, "data": audio_bytes}
                ])
        except Exception:
            with open(temp_file.name, 'rb') as f:
                audio_bytes = f.read()
            response = model.generate_content([
                transcription_prompt,
                {"mime_type": mime_type, "data": audio_bytes}
            ])

        if not response or not getattr(response, 'text', '').strip():
            raise ValueError("Gemini returned empty transcription")

        transcribed_text = response.text.strip()
        if len(transcribed_text) < 10:
            raise ValueError("Transcription too short - audio may be invalid or silent")

        return transcribed_text

    except TimeoutError as e:
        return f"Audio processing timeout: {str(e)}"
    except ValueError as e:
        return f"Invalid audio file: {str(e)}"
    except Exception as e:
        return f"Error transcribing audio: {str(e)}"
    finally:
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass


def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from PDF, DOCX, or TXT files
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    
    try:
        if ext == '.pdf':
            return extract_from_pdf(file_path)
        elif ext == '.docx':
            return extract_from_docx(file_path)
        elif ext == '.txt':
            return extract_from_txt(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    except Exception as e:
        raise Exception(f"Error extracting text: {str(e)}")


def extract_from_pdf(file_path: str) -> str:
    """Extract text from PDF file"""
    import re
    try:
        reader = PdfReader(file_path)
        text = []
        
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                # Fix letter-split text by normalizing excessive whitespace
                # Replace multiple spaces with single space
                cleaned = re.sub(r' {2,}', ' ', page_text)
                # Remove spaces between single characters (common PDF extraction issue)
                # Pattern: single char + space + single char
                cleaned = re.sub(r'\b(\w) +(\w)\b', r'\1\2', cleaned)
                text.append(cleaned)
        
        return "\n\n".join(text)
    except Exception as e:
        raise Exception(f"PDF extraction error: {str(e)}")


def extract_from_docx(file_path: str) -> str:
    """Extract text from DOCX file"""
    try:
        doc = Document(file_path)
        text = []
        
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text.append(paragraph.text)
        
        return "\n\n".join(text)
    except Exception as e:
        raise Exception(f"DOCX extraction error: {str(e)}")


def extract_from_txt(file_path: str) -> str:
    """Extract text from TXT file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise Exception(f"TXT extraction error: {str(e)}")


# ========== NEW: VECTOR STORE FUNCTIONS ==========

class VectorStoreManager:
    """Simple vector store for internal solutions"""
    
    def __init__(self):
        if not VECTOR_ENABLED:
            self.enabled = False
            return
            
        self.enabled = True
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.index = None
        self.solution_ids = []
        
        # Paths
        os.makedirs('vector_store', exist_ok=True)
        self.index_path = 'vector_store/solutions.index'
        self.ids_path = 'vector_store/solution_ids.json'
    
    def create_embedding_from_pdf(self, pdf_path: str, name: str, description: str) -> dict:
        """Create solution data with embedding from PDF"""
        if not self.enabled:
            return {'name': name, 'description': description, 'embedding': []}
        
        # Extract text
        full_text = extract_text_from_file(pdf_path)
        
        # Combine for embedding
        combined = f"Name: {name}\nDescription: {description}\n\n{full_text[:3000]}"
        
        # Create embedding
        embedding = self.model.encode(combined).tolist()
        
        return {
            'name': name,
            'description': description,
            'documentation': full_text[:5000],  # First 5000 chars
            'embedding': embedding,
            'technical_stack': self._extract_tech_stack(full_text),
            'features': self._extract_features(full_text)
        }
    
    def _extract_tech_stack(self, text: str) -> dict:
        """Simple tech stack extraction"""
        text_lower = text.lower()
        
        tech = {
            'frontend': [],
            'backend': [],
            'database': [],
            'ai': []
        }
        
        keywords = {
            'frontend': ['react', 'vue', 'angular', 'tailwind', 'bootstrap'],
            'backend': ['django', 'flask', 'fastapi', 'node', 'express'],
            'database': ['postgresql', 'mysql', 'mongodb', 'redis', 'sqlite'],
            'ai': ['langchain', 'openai', 'gemini', 'faiss', 'pytorch']
        }
        
        for category, words in keywords.items():
            found = [w for w in words if w in text_lower]
            if found:
                tech[category] = found
        
        return tech
    
    def _extract_features(self, text: str) -> list:
        """Extract feature list from text"""
        features = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            # Look for bullet points or numbered lists
            if line.startswith(('-', '•', '*')) or (line and line[0].isdigit()):
                feature = line.lstrip('-•*0123456789. ')
                if 10 < len(feature) < 150:
                    features.append(feature)
        
        return features[:15]  # Top 15 features
    
    def build_index(self):
        """Build FAISS index from database"""
        if not self.enabled:
            return
        
        from .models import InternalSolution
        
        solutions = InternalSolution.objects.all()
        if not solutions.exists():
            print("No solutions to index")
            return
        
        embeddings = []
        solution_ids = []
        
        for sol in solutions:
            if sol.embedding:
                embeddings.append(sol.embedding)
                solution_ids.append(sol.id)
        
        if not embeddings:
            print("No embeddings found")
            return
        
        # Create FAISS index
        embeddings_np = np.array(embeddings, dtype='float32')
        dimension = embeddings_np.shape[1]
        
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings_np)
        self.solution_ids = solution_ids
        
        # Save
        faiss.write_index(self.index, self.index_path)
        with open(self.ids_path, 'w') as f:
            json.dump(solution_ids, f)
        
        print(f"✅ Indexed {len(solution_ids)} solutions")
    
    def load_index(self):
        """Load existing index"""
        if not self.enabled:
            return
        
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.ids_path, 'r') as f:
                self.solution_ids = json.load(f)
            print(f"✅ Loaded {len(self.solution_ids)} solutions")
        else:
            self.build_index()
    
    def search_similar(self, project_text: str, top_k: int = 4) -> list:
        """Search for similar solutions"""
        if not self.enabled or self.index is None:
            self.load_index()
        
        if self.index is None:
            return []
        
        from .models import InternalSolution
        
        # Create query embedding
        query_emb = self.model.encode(project_text)
        query_emb = np.array([query_emb], dtype='float32')
        
        # Search
        distances, indices = self.index.search(query_emb, top_k)
        
        results = []
        for idx, distance in zip(indices[0], distances[0]):
            if idx < len(self.solution_ids):
                sol_id = self.solution_ids[idx]
                solution = InternalSolution.objects.get(id=sol_id)
                
                # Convert distance to similarity (0-100)
                similarity = max(0, 100 - (distance * 10))
                
                results.append({
                    'id': solution.id,
                    'name': solution.name,
                    'description': solution.description,
                    'features': solution.features,
                    'technical_stack': solution.technical_stack,
                    'relevance_score': round(similarity, 1)
                })
        
        return results


# Global instance
vector_store = VectorStoreManager()