const chat = document.getElementById('chat');
const form = document.getElementById('chat-form');
const question = document.getElementById('question');
const trace = document.getElementById('trace');
const dialogueState = document.getElementById('dialogue-state');
const resetButton = document.getElementById('reset-conversation');
const monthNames = [
  '', 'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

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

async function ask(text) {
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
    addMessage(data.answer || 'No answer returned.', 'bot');
    trace.textContent = data.debug ? formatDebug(data.debug) : (data.trace || []).join('\n');
    if (data.dialogue_state) dialogueState.textContent = formatDialogueState(data.dialogue_state);
  } catch (error) {
    addMessage(`Error: ${error.message}`, 'bot');
    trace.textContent = `Request failed: ${error.message}`;
  } finally {
    question.disabled = false;
    question.focus();
  }
}

form.addEventListener('submit', e => {
  e.preventDefault();
  ask(question.value);
});

document.querySelectorAll('.chip').forEach(button => {
  button.addEventListener('click', () => ask(button.dataset.q));
});

resetButton.addEventListener('click', async () => {
  resetButton.disabled = true;
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

addMessage('Hello! I am Version 3. I use transparent intent and entity rules, and remember relevant details during this conversation.', 'bot');
dialogueState.textContent = formatDialogueState(window.initialDialogueState || {});
