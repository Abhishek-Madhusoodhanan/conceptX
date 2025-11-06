import React, { useState, useRef, useEffect } from 'react';
import { Send, FileText, Download, Loader2, CheckCircle, Database, X, Paperclip, Mic } from 'lucide-react';
import * as API from './services/api';
import './App.css';

/* ---------- Structured Question Component (one-by-one capable) ---------- */
const QuestionList = ({ questions, onSkipAll, onSubmit }) => {
  const [answers, setAnswers] = React.useState(() => {
    const map = new Map();
    (questions || []).forEach((q) => map.set(q.id, ''));
    return map;
  });
  const [skipped, setSkipped] = React.useState(() => new Set());

  if (!questions || questions.length === 0) return null;

  const handleChange = (id, val) => {
    const next = new Map(answers);
    next.set(id, val);
    setAnswers(next);
    if (val && skipped.has(id)) {
      const s = new Set(skipped);
      s.delete(id);
      setSkipped(s);
    }
  };

  const toggleSkip = (id) => {
    const s = new Set(skipped);
    if (s.has(id)) s.delete(id);
    else s.add(id);
    setSkipped(s);
    if (s.has(id)) {
      const next = new Map(answers);
      next.set(id, '');
      setAnswers(next);
    }
  };

  const handleProceed = () => {
    const payload = questions.map((q) => ({
      id: q.id,
      question: q.question,
      answer: answers.get(q.id) || '',
      skipped: skipped.has(q.id),
    }));
    onSubmit?.(payload);
  };

  return (
    <div className="structured-questions">
      <h4 className="questions-title">
        Structured Clarification Questions ({questions.length})
      </h4>
      <ul className="questions-list">
        {questions.map((q) => (
          <li key={q.id} className="question-item">
            <span className="question-text">{q.question}</span>
            {q.why_asking && <span className="question-hint">💡 {q.why_asking}</span>}
            <textarea
              className="input-textarea"
              rows="3"
              placeholder="Type your answer for this question..."
              value={answers.get(q.id) || ''}
              onChange={(e) => handleChange(q.id, e.target.value)}
              disabled={skipped.has(q.id)}
              style={{ marginTop: 8 }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <button className="btn-skip" onClick={() => toggleSkip(q.id)}>
                {skipped.has(q.id) ? 'Unskip' : 'Skip this question'}
              </button>
            </div>
          </li>
        ))}
      </ul>
      <div className="questions-actions">
        <p className="helper-text-q">You can answer selectively. Skipped questions will be marked as such.</p>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={onSkipAll} className="btn-skip">
            Skip All
          </button>
          <button onClick={handleProceed} className="send-button">
            Proceed
          </button>
        </div>
      </div>
    </div>
  );
};

/* ---------------------------------- App ---------------------------------- */
function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [uploadedFile, setUploadedFile] = useState(null);
  const [currentProject, setCurrentProject] = useState(null);
  const [artifacts, setArtifacts] = useState([]);
  const [selectedArtifact, setSelectedArtifact] = useState(null);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [loading, setLoading] = useState(false);
  const [internalSolutions, setInternalSolutions] = useState([]);
  const [selectedSolutions, setSelectedSolutions] = useState([]);
  const [showSolutionModal, setShowSolutionModal] = useState(false);

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const audioInputRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    fetchInternalSolutions();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  }, [input]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const msgTime = (m) =>
    new Date(m.timestamp || m.created_at || Date.now()).toLocaleTimeString();

  const fetchInternalSolutions = async () => {
    try {
      const solutions = await API.getInternalSolutions();
      setInternalSolutions(solutions);
    } catch (error) {
      console.error('Error fetching solutions:', error);
    }
  };

  /* ----------------------- Clarification: Skip All flow ----------------------- */
  const handleSkipClarification = async () => {
    if (!currentProject) return;

    try {
      setLoading(true);

      const skipMessage =
        'I have enough information for now, please proceed to the solution proposal stage.';
      const updatedProject = await API.sendMessage(currentProject.id, skipMessage);

      setCurrentProject(updatedProject);
      setMessages(updatedProject.messages);
      setArtifacts(updatedProject.artifacts || []);

      const existingArtifacts = (updatedProject.artifacts ?? []).slice();

      if (existingArtifacts.length > 0) {
        const sortedArtifacts = existingArtifacts.sort(
          (a, b) => new Date(b.created_at) - new Date(a.created_at)
        );

        let previewArtifact =
          sortedArtifacts.find((a) => a.metadata?.type === 'summary_preview') ??
          sortedArtifacts[0];

        if (previewArtifact) {
          setArtifacts(sortedArtifacts);
          setTimeout(() => {
            setSelectedArtifact(previewArtifact);
            setShowArtifacts(true);
          }, 100);
          return;
        }
      }

      if (updatedProject.status === 'processing') {
        const fallbackContent = `# Project Summary Preview

## Project Overview

${currentProject.title}

## Collected Information

${messages.filter((m) => m.role === 'user').map((m) => m.content).join('\n\n')}

## Next Steps

Please proceed to select internal solutions to incorporate into your concept note.`;

        const fallbackArtifact = {
          id: 'fallback-' + Date.now(),
          title: `${currentProject.title} - Project Summary Preview`,
          content: fallbackContent,
          version: 'v0.1',
          status: 'preview',
          metadata: { type: 'summary_preview', editable: true },
          created_at: new Date().toISOString(),
        };

        const updatedArtifacts = [fallbackArtifact, ...existingArtifacts];
        setArtifacts(updatedArtifacts);
        setSelectedArtifact(fallbackArtifact);
        setShowArtifacts(true);
      }
    } catch (error) {
      console.error('Error skipping clarification:', error);
    } finally {
      setLoading(false);
    }
  };

  /* ------------------------------ Upload Document ----------------------------- */
 const handleFileUpload = async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  setLoading(true);
  setUploadedFile(file);

  // Don't wipe chat; append a processing system message
  const processingMessage = {
    role: 'system',
    content: `📄 Processing "${file.name}"... Please wait while I analyze the document.`,
  };
  setMessages(prev => (currentProject ? [...prev, processingMessage] : [processingMessage]));

  try {
    const title = file.name.replace(/\.[^/.]+$/, '');
    const project = currentProject
      ? await API.uploadDocumentToProject(currentProject.id, file) // existing project → keep chat
      : await API.uploadDocument(file, title);                     // new project

    setCurrentProject(project);
    setMessages(project.messages);
  } catch (error) {
    console.error('Error uploading file:', error);
    alert('Failed to upload file');
    if (!currentProject) setMessages([]); // only clear if no project existed
  } finally {
    setLoading(false);
  }
};

  /* ---------------------------------- Send ---------------------------------- */
  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);

    try {
      // If no project yet, create from text first
      if (!currentProject) {
        const title = userMessage.split('\n')[0].slice(0, 60) || 'Untitled Project';
        const project = await API.createProjectFromText(title, userMessage);
        setCurrentProject(project);
        setMessages(project.messages);
        return; // wait for user to continue conversation
      }

      const updatedProject = await API.sendMessage(currentProject.id, userMessage);
      setCurrentProject(updatedProject);
      setMessages(updatedProject.messages);
      setArtifacts(updatedProject.artifacts || []);

      const existingArtifacts = (updatedProject.artifacts ?? []).slice();
      if (existingArtifacts.length > 0) {
        const sortedArtifacts = existingArtifacts.sort(
          (a, b) => new Date(b.created_at) - new Date(a.created_at)
        );

        let previewArtifact =
          sortedArtifacts.find((a) => a.metadata?.type === 'summary_preview') ??
          sortedArtifacts[0];

        if (previewArtifact) {
          setArtifacts(sortedArtifacts);
          setTimeout(() => {
            setSelectedArtifact(previewArtifact);
            setShowArtifacts(true);
          }, 100);
        }
      }
    } catch (error) {
      console.error('Error sending message:', error);
    } finally {
      setLoading(false);
    }
  };

  /* ----------------------------- Solutions modal ----------------------------- */
  const handleSolutionToggle = (solutionId) => {
    setSelectedSolutions((prev) =>
      prev.includes(solutionId) ? prev.filter((id) => id !== solutionId) : [...prev, solutionId]
    );
  };

  const handleGenerateConceptNote = async () => {
    if (!currentProject) {
      console.error('❌ No current project!');
      return;
    }

    setLoading(true);
    setShowSolutionModal(false);

    try {
      const updatedProject = await API.generateConceptNote(
        currentProject.id,
        selectedSolutions
      );

      setCurrentProject(updatedProject);
      setMessages(updatedProject.messages);
      setArtifacts(updatedProject.artifacts || []);

      const existingArtifacts = (updatedProject.artifacts ?? []).slice();
      if (existingArtifacts.length > 0) {
        const sortedArtifacts = existingArtifacts.sort(
          (a, b) => new Date(b.created_at) - new Date(a.created_at)
        );

        const latestArtifact = sortedArtifacts[0];
        if (latestArtifact) {
          setSelectedArtifact(latestArtifact);
          setShowArtifacts(true);

          setTimeout(() => {
            setArtifacts(sortedArtifacts); // Trigger re-render if needed
          }, 100);
        }
      } else {
        alert('No concept note was generated. Please try again.');
      }
    } catch (error) {
      console.error('❌ Error generating concept note:', error);
      alert('Failed to generate concept note: ' + (error.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  /* ------------------------------ Artifact actions --------------------------- */
  const handleConfirmArtifact = async () => {
    if (!selectedArtifact) return;

    try {
      await API.updateArtifact(selectedArtifact.id, { status: 'confirmed' });

      const updatedProject = await API.getProject(currentProject.id);
      setCurrentProject(updatedProject);
      setMessages(updatedProject.messages);
      setArtifacts(updatedProject.artifacts);
      setSelectedArtifact(updatedProject.artifacts[0]);
      setShowArtifacts(false); // hide panel after confirming

      if (selectedArtifact.metadata?.type === 'summary_preview') {
        setShowSolutionModal(true);
      }
    } catch (error) {
      console.error('Error confirming artifact:', error);
    }
  };

  const handleEditArtifact = async (newContent) => {
    if (!selectedArtifact) return;

    try {
      await API.updateArtifact(selectedArtifact.id, { content: newContent });
      setSelectedArtifact({ ...selectedArtifact, content: newContent });
    } catch (error) {
      console.error('Error updating artifact:', error);
    }
  };

  /* -------------------- Derived questions (one at a time) -------------------- */
  const clarificationQuestions =
    currentProject?.context_data?.clarification_questions ?? [];

  const visibleQuestions = clarificationQuestions.slice(0, 1);

  return (
    <div className={`app ${showArtifacts ? 'artifacts-open' : ''}`}>
      {/* Main Chat Area */}
      <div className="chat-container">
        {/* Header */}
        <div className="header">
          <div className="header-inner">
            <div>
              <h1 className="header-title">Concept-X</h1>
              <p className="header-subtitle">AI Conversational Workflow System</p>
            </div>
            {uploadedFile && null}
          </div>
        </div>

        {/* Messages Area */}
        <div className={`messages ${messages.length === 0 ? 'welcome-center' : ''}`}>
          <div className="messages-inner">
            {messages.length === 0 && (
              <div className="welcome">
                <div>
                  <div className="welcome-icon">
                    <FileText className="icon-lg invert" />
                  </div>
                  <h2 className="welcome-title">Welcome to Concept-X</h2>
                  <p className="welcome-subtitle">
                    Upload a document to create your AI-powered concept note
                  </p>
                  <div className="welcome-tips">
                    <p className="mb-2">
                      💡 Use the attachment button below to upload PDF, DOCX, or TXT files
                    </p>
                    <p>🎤 Or use voice input to describe your project</p>
                  </div>
                </div>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div key={idx} className={`message-row ${msg.role}`}>
                <div className={`message-bubble ${msg.role}`}>
                  {msg.role === 'assistant' && (
                    <div className="assistant-label">
                      <div className="assistant-avatar">AI</div>
                      <span>Concept-X Assistant</span>
                    </div>
                  )}
                  {msg.role === 'system' && msg.content?.includes('Processing') && (
                    <div className="processing-spinner"></div>
                  )}
                  <p className="message-text">{msg.content}</p>
                  <div className="message-time">{msgTime(msg)}</div>
                </div>
              </div>
            ))}

            {/* Structured Clarification Questions (one at a time) */}
            {visibleQuestions.length > 0 && (
              <QuestionList
                questions={visibleQuestions}
                onSkipAll={handleSkipClarification}
                onSubmit={async (answers) => {
                  try {
                    setLoading(true);

                    const content = `__CLARIFICATION_SUBMISSION__::${JSON.stringify(
                      answers.reduce((acc, a) => {
                        acc[a.id] = a.skipped ? 'NO_RESPONSE_SKIPPED' : a.answer;
                        return acc;
                      }, {})
                    )}`;

                    const updatedProject = await API.sendMessage(currentProject.id, content);

                    setCurrentProject(updatedProject);
                    setMessages(updatedProject.messages);
                    setArtifacts(updatedProject.artifacts || []);

                    const existingArtifacts = (updatedProject.artifacts ?? []).slice();

                    if (existingArtifacts.length > 0) {
                      const sortedArtifacts = existingArtifacts.sort(
                        (a, b) => new Date(b.created_at) - new Date(a.created_at)
                      );

                      let previewArtifact =
                        sortedArtifacts.find((a) => a.metadata?.type === 'summary_preview') ??
                        sortedArtifacts[0];

                      if (previewArtifact) {
                        setArtifacts(sortedArtifacts);
                        setTimeout(() => {
                          setSelectedArtifact(previewArtifact);
                          setShowArtifacts(true);
                        }, 100);
                        return;
                      }
                    }

                    if (updatedProject.status === 'processing') {
                      const fallbackArtifact = {
                        id: 'fallback-' + Date.now(),
                        title: `${currentProject.title} - Project Summary Preview`,
                        content: `# Project Summary Preview

## Project Overview

${currentProject.title}

## Collected Information

${messages.filter((m) => m.role === 'user').map((m) => m.content).join('\n\n')}

## Next Steps

Please proceed to select internal solutions to incorporate into your concept note.`,
                        version: 'v0.1',
                        status: 'preview',
                        metadata: { type: 'summary_preview', editable: true },
                        created_at: new Date().toISOString(),
                      };

                      const updatedArtifacts = [fallbackArtifact, ...existingArtifacts];
                      setArtifacts(updatedArtifacts);
                      setSelectedArtifact(fallbackArtifact);
                      setShowArtifacts(true);
                    }
                  } catch (err) {
                    console.error('❌ Submitting answers failed', err);
                  } finally {
                    setLoading(false);
                  }
                }}
              />
            )}

            {loading && currentProject && (
              <div className="loader">
                <div className="loader-box">
                  <Loader2 className="spinner" />
                  <span>Processing...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className="input-bar">
          <div className="input-inner">
            <div className="input-row">
              <div className="input-actions">
                {currentProject &&
                  currentProject.artifacts &&
                  currentProject.artifacts.length > 0 && (
                    <button
                      onClick={() => {
                        const artifact = currentProject.artifacts[0];
                        setSelectedArtifact(artifact);
                        setShowArtifacts(true);
                      }}
                      className="icon-button"
                      title="Debug: Show Artifact"
                      style={{ background: '#f0f9ff' }}
                    >
                      <FileText className="icon-md" style={{ color: '#3b82f6' }} />
                    </button>
                  )}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={loading}
                  className="icon-button"
                  title="Upload document"
                >
                  <Paperclip className="icon-md" />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,.txt"
                  onChange={handleFileUpload}
                  className="visually-hidden"
                />

                <button
                  className="icon-button"
                  title="Voice input"
                  onClick={() => audioInputRef.current?.click()}
                >
                  <Mic className="icon-md" />
                </button>
                <input
                  ref={audioInputRef}
                  type="file"
                  accept=".mp3,.wav,.m4a,.flac,.aac,.ogg,audio/*"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    try {
                      setLoading(true);
                      const res = await API.transcribeAudio(file);
                      if (res && res.text) {
                        setInput((prev) => (prev ? prev + '\n' : '') + res.text);
                      } else if (res && res.error) {
                        alert(res.error);
                      }
                    } catch (err) {
                      console.error('Audio transcribe failed', err);
                      alert('Failed to transcribe audio');
                    } finally {
                      setLoading(false);
                      e.target.value = '';
                    }
                  }}
                  className="visually-hidden"
                />
              </div>

              <textarea
                ref={textareaRef}
                rows="1"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Type your response..."
                className="input-textarea"
                disabled={loading}
              />

              <button onClick={handleSend} disabled={!input.trim() || loading} className="send-button">
                <Send className="icon-md" />
              </button>
            </div>

            {!currentProject && <p className="helper-text">Upload a document to begin</p>}
          </div>
        </div>
      </div>

      {/* Solution Selection Modal */}
      {showSolutionModal && (
        <div className="modal-backdrop">
          <div className="modal">
            <div className="modal-header">
              <h3 className="modal-title">
                <Database className="icon-lg primary" />
                Select Internal Solutions
              </h3>
              <button onClick={() => setShowSolutionModal(false)} className="icon-button subtle">
                <X className="icon-lg" />
              </button>
            </div>

            <div className="modal-body">
              {internalSolutions.map((sol) => (
                <label key={sol.id} className="solution-item">
                  <input
                    type="checkbox"
                    checked={selectedSolutions.includes(sol.id)}
                    onChange={() => handleSolutionToggle(sol.id)}
                    className="checkbox-lg"
                  />
                  <div className="flex-1">
                    <div className="solution-name">{sol.name}</div>
                    <div className="solution-desc">{sol.description}</div>
                  </div>
                </label>
              ))}
            </div>

            <div className="modal-footer">
              <button
                onClick={() => {
                  handleGenerateConceptNote();
                }}
                className="btn-primary btn-block"
                disabled={loading}
              >
                {loading
                  ? 'Generating...'
                  : `Generate Concept Note (${selectedSolutions.length} selected)`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Artifacts Panel */}
      {showArtifacts && selectedArtifact && (
        <div className={`artifacts-panel ${showArtifacts ? 'open' : ''}`}>
          <div className="artifacts-header">
            <div className="artifacts-header-row">
              <h2 className="artifacts-title">
                <FileText className="icon-md invert" />
                Artifact Preview
              </h2>
              <button onClick={() => setShowArtifacts(false)} className="artifacts-close">
                <X className="icon-md" />
              </button>
            </div>
            <div className="artifacts-subtitle">{selectedArtifact.title}</div>
          </div>

          <div className="artifacts-content">
            <textarea
              value={selectedArtifact.content}
              onChange={(e) => handleEditArtifact(e.target.value)}
              className="artifacts-textarea"
            />
          </div>

          <div className="artifacts-footer">
            <div className="artifact-status">
              <span className="version">{selectedArtifact.version}</span>
              <span className={`status-pill ${selectedArtifact.status}`}>
                {selectedArtifact.status === 'confirmed' ? '✓ Confirmed' : '⏳ Preview'}
              </span>
              <button
                onClick={() => {
                  console.log('Artifact details:', selectedArtifact);
                  console.log('Artifact metadata:', selectedArtifact.metadata);
                  console.log('All artifacts state:', artifacts);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#888',
                  fontSize: '12px',
                  cursor: 'pointer',
                }}
              >
                Debug
              </button>
            </div>

            {selectedArtifact.status === 'preview' && (
              <button
                onClick={() => {
                  setShowArtifacts(false);
                  setTimeout(() => setShowSolutionModal(true), 100);
                }}
                className="btn-confirm btn-block"
              >
                <CheckCircle className="icon-md" />
                Proceed to Solution Selection
              </button>
            )}

            {selectedArtifact.status === 'preview' &&
              selectedArtifact.metadata?.type === 'concept_note' && (
                <button onClick={handleConfirmArtifact} className="btn-confirm btn-block">
                  <CheckCircle className="icon-md" />
                  Confirm Concept Note
                </button>
              )}

            {selectedArtifact.status === 'confirmed' && (
              <button className="btn-download btn-block">
                <Download className="icon-md" />
                Download PDF
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
