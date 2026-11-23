const chat = document.getElementById('chat');
const form = document.getElementById('chat-form');
const question = document.getElementById('question');
const trace = document.getElementById('trace');
const dialogueState = document.getElementById('dialogue-state');
const resetButton = document.getElementById('reset-conversation');
const voiceButton = document.getElementById('voice-button');
const voiceStatus = document.getElementById('voice-status');
const speakBack = document.getElementById('speakBack');
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const monthNames = [
  '', 'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];
let recognition = null;
let listening = false;

function formatDebug(debug) {
  const entities = debug.entities || {};
  const labels = {
    month: 'Month',
    relative_date: 'Relative date',
    relative_month: 'Relative month',
    relationship: 'Relationship',
    person_name: 'Person',
    person_id: 'Person ID'
  };
  const lines = [`Intent: ${debug.intent}`, 'Entities:'];
  const entries = Object.entries(entities);
  if (!entries.length) lines.push('- None');
  for (const [key, value] of entries) {
    const displayValue = key === 'month' ? `${monthNames[value] || value} (${value})` : value;
    lines.push(`- ${labels[key] || key}: ${displayValue}`);
  }
  if (debug.ambiguity && debug.ambiguity.includes('person')) {
    lines.push('- Person match: ambiguous; no person was selected');
  }
  if (debug.nlu_method) lines.push(`NLU method: ${debug.nlu_method}`);
  if (debug.grounding_status) lines.push(`Grounding: ${debug.grounding_status}`);
  return lines.join('\n');
}

function formatDialogueState(state) {
  const fields = [
    ['Remembered month', state.month ? `${monthNames[state.month] || state.month} (${state.month})` : 'None'],
    ['Remembered relationship', state.relationship || 'None'],
    ['Person', state.person_name || state.person_id || 'None'],
    ['Last result IDs', (state.last_result_ids || []).join(', ') || 'None'],
    ['Clarification pending', state.pending_clarification ? 'Yes' : 'No']
  ];
  return fields.map(([label, value]) => `${label}: ${value}`).join('\n');
}

function addMessage(text, role) {
  const row = document.createElement('div');
  row.className = `message ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  row.appendChild(bubble);
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

function setVoiceStatus(message, isListening = false) {
  voiceStatus.textContent = message;
  voiceStatus.classList.toggle('is-listening', isListening);
}

function readResponseAloud(text) {
  if (!speakBack.checked) return;
  if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
    setVoiceStatus('Speech output is not supported in this browser. The text response is still available.');
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-IN';
  utterance.onerror = () => setVoiceStatus('The browser could not read this response aloud. The text response is still available.');
  window.speechSynthesis.speak(utterance);
}

async function sendMsg(text = question.value) {
  text = text.trim();
  if (!text) return;
  addMessage(text, 'user');
  question.value = '';
  question.disabled = true;
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const answer = data.answer || 'No answer returned.';
    addMessage(answer, 'bot');
    trace.textContent = data.debug ? formatDebug(data.debug) : (data.trace || []).join('\n');
    if (data.dialogue_state) dialogueState.textContent = formatDialogueState(data.dialogue_state);
    readResponseAloud(answer);
  } catch (error) {
    addMessage(`Error: ${error.message}`, 'bot');
    trace.textContent = `Request failed: ${error.message}`;
  } finally {
    question.disabled = false;
    question.focus();
  }
}

function startListening() {
  if (!SpeechRecognition) {
    setVoiceStatus('Speech recognition is not supported in this browser. You can still type your question.');
    return;
  }
  if (!window.isSecureContext && !['localhost', '127.0.0.1', '::1'].includes(location.hostname)) {
    setVoiceStatus('Microphone access requires HTTPS or localhost. You can still type your question.');
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'en-IN';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  let receivedResult = false;
  let recognitionFailed = false;

  recognition.onstart = () => {
    listening = true;
    voiceButton.textContent = 'Stop listening';
    voiceButton.setAttribute('aria-pressed', 'true');
    setVoiceStatus('Listening… Speak your question now.', true);
  };

  recognition.onresult = event => {
    const transcript = event.results[0][0].transcript.trim();
    receivedResult = true;
    if (!transcript) {
      setVoiceStatus('No words were recognized. Try speaking again or type your question.');
      return;
    }
    question.value = transcript;
    setVoiceStatus(`Recognized: “${transcript}”`);
    sendMsg(transcript);
  };

  recognition.onerror = event => {
    recognitionFailed = true;
    const messages = {
      'not-allowed': 'Microphone access was denied. Allow microphone access in your browser settings, or type your question.',
      'service-not-allowed': 'The browser speech service is unavailable. You can still type your question.',
      'audio-capture': 'No microphone was found. Connect a microphone or type your question.',
      'no-speech': 'No speech was detected. Try again, or type your question.',
      'network': 'The browser speech recognition service had a network error. You can still type your question.',
      'aborted': 'Voice input was stopped.'
    };
    setVoiceStatus(messages[event.error] || `Voice input failed (${event.error}). You can still type your question.`);
  };

  recognition.onend = () => {
    listening = false;
    voiceButton.textContent = 'Speak';
    voiceButton.setAttribute('aria-pressed', 'false');
    if (!receivedResult && !recognitionFailed) {
      setVoiceStatus('Voice input ended without a transcript. Try again or type your question.');
    } else {
      voiceStatus.classList.remove('is-listening');
    }
  };

  try {
    recognition.start();
  } catch (error) {
    listening = false;
    voiceButton.textContent = 'Speak';
    voiceButton.setAttribute('aria-pressed', 'false');
    setVoiceStatus(`Could not start voice input: ${error.message}. You can still type your question.`);
  }
}

form.addEventListener('submit', event => {
  event.preventDefault();
  sendMsg();
});

document.querySelectorAll('.chip').forEach(button => {
  button.addEventListener('click', () => sendMsg(button.dataset.q));
});

voiceButton.addEventListener('click', () => {
  if (listening) {
    recognition.stop();
    return;
  }
  startListening();
});

const unavailableVoiceFeatures = [];
if (!SpeechRecognition) {
  voiceButton.disabled = true;
  unavailableVoiceFeatures.push('speech recognition');
}

if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
  speakBack.disabled = true;
  unavailableVoiceFeatures.push('speech output');
}
if (unavailableVoiceFeatures.length) {
  setVoiceStatus(`${unavailableVoiceFeatures.join(' and ')} ${unavailableVoiceFeatures.length === 1 ? 'is' : 'are'} not supported in this browser. Text chat remains available.`);
}

resetButton.addEventListener('click', async () => {
  resetButton.disabled = true;
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  try {
    const response = await fetch('/reset', {method: 'POST'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data.success) throw new Error('The server did not reset the conversation.');
    chat.replaceChildren();
    addMessage(data.answer || 'Conversation reset.', 'bot');
    trace.textContent = 'Conversation reset.';
    dialogueState.textContent = formatDialogueState(data.dialogue_state || {});
  } catch (error) {
    addMessage(`Reset failed: ${error.message}`, 'bot');
  } finally {
    resetButton.disabled = false;
  }
});

addMessage('Hello! I am Version 5. Type or speak a question. Your transcript and my answer will remain visible.', 'bot');
dialogueState.textContent = formatDialogueState(window.initialDialogueState || {});
