import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { createTask, getProjectMembers } from '../api/client';
import { ru } from '../locales/ru';

function CreateTaskModal({ projectId, onClose, onCreated }) {
  const [description, setDescription] = useState('');
  const [assigneeId, setAssigneeId] = useState('');
  const [priority, setPriority] = useState('normal');
  const [dueDate, setDueDate] = useState('');
  const [members, setMembers] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadMembers();
  }, [projectId]);

  const loadMembers = async () => {
    try {
      const res = await getProjectMembers(projectId);
      setMembers(res.data);
      if (res.data.length > 0) {
        setAssigneeId(res.data[0].user_id.toString());
      }
    } catch (err) {
      console.error('Failed to load members:', err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!description.trim() || !assigneeId) return;

    setSubmitting(true);
    setError('');
    try {
      await createTask({
        project_id: parseInt(projectId),
        assignee_id: parseInt(assigneeId),
        description: description.trim(),
        priority,
        due_date: dueDate || null,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || ru.errors.saveFailed);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-lg">
        <div className="flex items-center justify-between p-6 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white">{ru.task.newTask}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="bg-red-500/20 text-red-400 px-4 py-2 rounded-lg text-sm">{error}</div>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-1">{ru.task.description}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              required
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder={ru.task.description}
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">{ru.task.assignee}</label>
            <select
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              required
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">{ru.task.selectAssignee}</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  @{m.user?.username || m.user?.full_name || `User #${m.user_id}`}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">{ru.task.priority}</label>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="low">{ru.priority.low}</option>
              <option value="normal">{ru.priority.normal}</option>
              <option value="high">{ru.priority.high}</option>
              <option value="urgent">{ru.priority.urgent}</option>
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">{ru.task.dueDate}</label>
            <input
              type="datetime-local"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex justify-end space-x-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 text-gray-300 hover:bg-gray-600 rounded-lg transition-colors"
            >
              {ru.actions.cancel}
            </button>
            <button
              type="submit"
              disabled={submitting || !description.trim() || !assigneeId}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              {submitting ? ru.common.loading : ru.actions.createTask}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CreateTaskModal;
