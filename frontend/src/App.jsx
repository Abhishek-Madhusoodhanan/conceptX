import React, { useState, useRef, useEffect } from 'react';
import { Upload, Send, FileText, Download, Loader2, CheckCircle, Database, X, Paperclip, Mic, Image } from 'lucide-react';
import * as API from './services/api';
import './App.css';

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

  const fetchInternalSolutions = async () => {
    try {
      const solutions = await API.getInternalSolutions();
      setInternalSolutions(solutions);
    } catch (error) {
      console.error('Error fetching solutions:', error);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    setUploadedFile(file);

    try {
      const title = file.name.replace(/\.[^/.]+$/, '');
      const project = await API.uploadDocument(file, title);
      
      setCurrentProject(project);
      setMessages(project.messages);
    } catch (error) {
      console.error('Error uploading file:', error);
      alert('Failed to upload file');
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading || !currentProject) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);

    try {
      const updatedProject = await API.sendMessage(currentProject.id, userMessage);
      setCurrentProject(updatedProject);
      setMessages(updatedProject.messages);

      // Check if ready for solution selection
      const userMessages = updatedProject.messages.filter(m => m.role === 'user');
      if (userMessages.length >= 4 && !showSolutionModal) {
        setTimeout(() => {
          setShowSolutionModal(true);
        }, 1000);
      }
    } catch (error) {
      console.error('Error sending message:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSolutionToggle = (solutionId) => {
    setSelectedSolutions(prev => 
      prev.includes(solutionId) 
        ? prev.filter(id => id !== solutionId)
        : [...prev, solutionId]
    );
  };

  const handleGenerateConceptNote = async () => {
    if (!currentProject) return;

    setLoading(true);
    setShowSolutionModal(false);

    try {
      const updatedProject = await API.generateConceptNote(
        currentProject.id,
        selectedSolutions
      );

      setCurrentProject(updatedProject);
      setMessages(updatedProject.messages);
      setArtifacts(updatedProject.artifacts);
      
      if (updatedProject.artifacts.length > 0) {
        setSelectedArtifact(updatedProject.artifacts[0]);
        setShowArtifacts(true);
      }
    } catch (error) {
      console.error('Error generating concept note:', error);
      alert('Failed to generate concept note');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmArtifact = async () => {
    if (!selectedArtifact) return;

    try {
      await API.updateArtifact(selectedArtifact.id, { status: 'confirmed' });
      
      const updatedProject = await API.getProject(currentProject.id);
      setCurrentProject(updatedProject);
      setMessages(updatedProject.messages);
      setArtifacts(updatedProject.artifacts);
      setSelectedArtifact(updatedProject.artifacts[0]);
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

  return (
    <div className="app">
      {/* Main Chat Area */}
      <div className="chat-container">
        {/* Header */}
        <div className="header">
          <div className="header-inner">
            <div>
              <h1 className="header-title">Concept-X</h1>
              <p className="header-subtitle">AI Conversational Workflow System</p>
            </div>
            {uploadedFile && (
              <div className="uploaded-file-badge">
                <FileText className="icon-sm" />
                {uploadedFile.name}
              </div>
            )}
          </div>
        </div>

        {/* Messages Area */}
        <div className="messages">
          <div className="messages-inner">
            {messages.length === 0 && (
              <div className="welcome">
                <div>
                  <div className="welcome-icon">
                    <FileText className="icon-lg invert" />
                  </div>
                  <h2 className="welcome-title">Welcome to Concept-X</h2>
                  <p className="welcome-subtitle">Upload a document to create your AI-powered concept note</p>
                  <div className="welcome-tips">
                    <p className="mb-2">💡 Use the attachment button below to upload PDF, DOCX, or TXT files</p>
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
                      <div className="assistant-avatar">
                        AI
                      </div>
                      <span>Concept-X Assistant</span>
                    </div>
                  )}
                  <p className="message-text">{msg.content}</p>
                  <div className="message-time">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}

            {loading && (
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
                  title="Upload image"
                >
                  <Image className="icon-md" />
                </button>
                
                <button
                  className="icon-button"
                  title="Voice input"
                >
                  <Mic className="icon-md" />
                </button>
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
                disabled={loading || !currentProject}
              />

              <button
                onClick={handleSend}
                disabled={!input.trim() || loading || !currentProject}
                className="send-button"
              >
                <Send className="icon-md" />
              </button>
            </div>
            
            {!currentProject && (
              <p className="helper-text">
                Upload a document to begin
              </p>
            )}
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
              {internalSolutions.map(sol => (
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
                onClick={handleGenerateConceptNote}
                className="btn-primary btn-block"
              >
                Generate Concept Note ({selectedSolutions.length} selected)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Artifacts Panel */}
      {showArtifacts && selectedArtifact && (
        <div className="artifacts-panel">
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
            </div>
            
            {selectedArtifact.status === 'preview' && (
              <button
                onClick={handleConfirmArtifact}
                className="btn-confirm btn-block"
              >
                <CheckCircle className="icon-md" />
                Confirm Concept Note
              </button>
            )}
            
            {selectedArtifact.status === 'confirmed' && (
              <button
                className="btn-download btn-block"
              >
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
