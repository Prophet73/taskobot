import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getTask, updateTask, deleteTask, getTaskComments, addTaskComment, getTaskHistory, getProject, getProjectMembers } from '../api/client';
import { ArrowLeft, MessageSquare, History, Send, User, Clock, Check, Play, FileCheck, Trash2, Pencil, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { ru } from '../locales/ru';

const statusConfig = {
  pending: { label: ru.status.pending, color: 'bg-yellow-500/20 text-yellow-400' },
  in_progress: { label: ru.status.in_progress, color: 'bg-blue-500/20 text-blue-400' },
  pending_review: { label: ru.status.pending_review, color: 'bg-purple-500/20 text-purple-400' },
  done: { label: ru.status.done, color: 'bg-green-500/20 text-green-400' },
  cancelled: { label: ru.status.cancelled, color: 'bg-gray-500/20 text-gray-400' },
};

const priorityConfig = {
  urgent: { label: ru.priority.urgent, color: 'bg-red-500' },
  high: { label: ru.priority.high, color: 'bg-orange-500' },
  normal: { label: ru.priority.normal, color: 'bg-green-500' },
  low: { label: ru.priority.low, color: 'bg-gray-500' },
};

const historyActionLabels = {
  created: ru.history.actions.created,
  status_changed: ru.history.actions.status_changed,
  assigned: ru.history.actions.assigned,
  reassigned: ru.history.actions.reassigned,
  comment_added: ru.history.actions.comment_added,
  priority_changed: ru.history.actions.priority_changed,
  due_date_changed: ru.history.actions.due_date_changed,
};

function TaskDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [task, setTask] = useState(null);
  const [comments, setComments] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newComment, setNewComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState('comments');
  const [isManager, setIsManager] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState({});
  const [members, setMembers] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadData();
  }, [id]);

  const loadData = async () => {
    try {
      const [taskRes, commentsRes, historyRes] = await Promise.all([
        getTask(id),
        getTaskComments(id),
        getTaskHistory(id),
      ]);
      setTask(taskRes.data);
      setComments(commentsRes.data);
      setHistory(historyRes.data);

      // Check if user is manager in this task's project
      try {
        const projectRes = await getProject(taskRes.data.project_id);
        const isMgr = user?.is_superadmin ||
          projectRes.data.members?.some(m => m.user_id === user?.id && (m.role === 'manager' || m.role === 'superadmin'));
        setIsManager(!!isMgr);
        if (isMgr) {
          try {
            const membersRes = await getProjectMembers(taskRes.data.project_id);
            setMembers(membersRes.data);
          } catch { /* ignore if members load fails */ }
        }
      } catch {
        setIsManager(user?.is_superadmin || false);
      }
    } catch (err) {
      console.error('Failed to load task:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (newStatus) => {
    try {
      await updateTask(task.id, { status: newStatus });
      loadData();
    } catch (err) {
      console.error('Failed to update task:', err);
    }
  };

  const handleAddComment = async (e) => {
    e.preventDefault();
    if (!newComment.trim()) return;

    setSubmitting(true);
    try {
      await addTaskComment(task.id, newComment.trim());
      setNewComment('');
      loadData();
    } catch (err) {
      console.error('Failed to add comment:', err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleStartEdit = () => {
    setEditData({
      description: task.description,
      assignee_id: task.assignee_id,
      priority: task.priority,
      due_date: task.due_date ? task.due_date.slice(0, 16) : '',
    });
    setEditing(true);
  };

  const handleCancelEdit = () => {
    setEditing(false);
    setEditData({});
  };

  const handleSaveEdit = async () => {
    setSaving(true);
    try {
      const payload = {};
      if (editData.description !== task.description) payload.description = editData.description;
      if (editData.assignee_id !== task.assignee_id) payload.assignee_id = editData.assignee_id;
      if (editData.priority !== task.priority) payload.priority = editData.priority;
      if (editData.due_date !== (task.due_date ? task.due_date.slice(0, 16) : '')) {
        payload.due_date = editData.due_date || null;
      }
      if (Object.keys(payload).length > 0) {
        await updateTask(task.id, payload);
      }
      setEditing(false);
      loadData();
    } catch (err) {
      console.error('Failed to save task:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(ru.task.deleteConfirm)) return;
    try {
      await deleteTask(task.id);
      navigate(`/projects/${task.project_id}`);
    } catch (err) {
      console.error('Failed to delete task:', err);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!task) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-400">{ru.errors.notFound}</p>
        <Link to="/tasks" className="text-blue-400 hover:underline mt-2 inline-block">
          {ru.common.back}
        </Link>
      </div>
    );
  }

  const status = statusConfig[task.status] || statusConfig.pending;
  const priority = priorityConfig[task.priority] || priorityConfig.normal;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center space-x-4">
        <Link to={`/projects/${task.project_id}`} className="text-gray-400 hover:text-white transition-colors">
          <ArrowLeft size={24} />
        </Link>
        <div className="flex-1">
          <div className="flex items-center space-x-3">
            <span className="text-gray-500">#{task.id}</span>
            <span className={`px-2 py-1 rounded text-sm ${status.color}`}>
              {status.label}
            </span>
            <span className={`w-3 h-3 rounded-full ${priority.color}`} title={priority.label}></span>
          </div>
        </div>
        {isManager && !editing && (
          <div className="flex space-x-2">
            <button
              onClick={handleStartEdit}
              className="flex items-center px-3 py-1.5 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 rounded-lg transition-colors text-sm"
            >
              <Pencil size={14} className="mr-1" />
              {ru.actions.edit}
            </button>
            <button
              onClick={handleDelete}
              className="flex items-center px-3 py-1.5 bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg transition-colors text-sm"
            >
              <Trash2 size={14} className="mr-1" />
              {ru.actions.deleteTask}
            </button>
          </div>
        )}
      </div>

      {/* Task Content */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        {editing ? (
          <>
            <div className="space-y-4 mb-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">{ru.task.description}</label>
                <textarea
                  value={editData.description}
                  onChange={(e) => setEditData({ ...editData, description: e.target.value })}
                  rows={3}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">{ru.task.assignee}</label>
                  <select
                    value={editData.assignee_id}
                    onChange={(e) => setEditData({ ...editData, assignee_id: parseInt(e.target.value) })}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
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
                    value={editData.priority}
                    onChange={(e) => setEditData({ ...editData, priority: e.target.value })}
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
                    value={editData.due_date}
                    onChange={(e) => setEditData({ ...editData, due_date: e.target.value })}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            </div>
            <div className="flex space-x-3 pt-4 border-t border-gray-700">
              <button
                onClick={handleSaveEdit}
                disabled={saving}
                className="flex items-center px-4 py-2 bg-green-600/20 text-green-400 hover:bg-green-600/30 rounded-lg transition-colors"
              >
                <Check size={16} className="mr-2" />
                {saving ? ru.common.loading : ru.actions.save}
              </button>
              <button
                onClick={handleCancelEdit}
                className="flex items-center px-4 py-2 bg-gray-700 text-gray-300 hover:bg-gray-600 rounded-lg transition-colors"
              >
                <X size={16} className="mr-2" />
                {ru.actions.cancel}
              </button>
            </div>
          </>
        ) : (
          <>
        <p className="text-xl text-white mb-4">{task.description}</p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">{ru.task.assignee}</span>
            <p className="text-white flex items-center mt-1">
              <User size={14} className="mr-1" />
              @{task.assignee?.username || task.assignee?.full_name || '—'}
            </p>
          </div>
          <div>
            <span className="text-gray-500">{ru.task.creator}</span>
            <p className="text-white flex items-center mt-1">
              <User size={14} className="mr-1" />
              @{task.creator?.username || task.creator?.full_name || '—'}
            </p>
          </div>
          <div>
            <span className="text-gray-500">{ru.task.created}</span>
            <p className="text-white flex items-center mt-1">
              <Clock size={14} className="mr-1" />
              {formatDate(task.created_at)}
            </p>
          </div>
          {task.due_date && (
            <div>
              <span className="text-gray-500">{ru.task.dueDate}</span>
              <p className="text-white flex items-center mt-1">
                <Clock size={14} className="mr-1" />
                {formatDate(task.due_date)}
              </p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex space-x-3 mt-6 pt-4 border-t border-gray-700">
          {task.status === 'pending' && (
            <button
              onClick={() => handleStatusChange('in_progress')}
              className="flex items-center px-4 py-2 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 rounded-lg transition-colors"
            >
              <Play size={16} className="mr-2" />
              {ru.actions.start}
            </button>
          )}
          {task.status === 'in_progress' && (
            <button
              onClick={() => handleStatusChange('pending_review')}
              className="flex items-center px-4 py-2 bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 rounded-lg transition-colors"
            >
              <FileCheck size={16} className="mr-2" />
              {ru.actions.toReview}
            </button>
          )}
          {task.status === 'pending_review' && isManager && (
            <>
              <button
                onClick={() => handleStatusChange('done')}
                className="flex items-center px-4 py-2 bg-green-600/20 text-green-400 hover:bg-green-600/30 rounded-lg transition-colors"
              >
                <Check size={16} className="mr-2" />
                {ru.actions.approve}
              </button>
              <button
                onClick={() => handleStatusChange('in_progress')}
                className="flex items-center px-4 py-2 bg-orange-600/20 text-orange-400 hover:bg-orange-600/30 rounded-lg transition-colors"
              >
                {ru.actions.reject}
              </button>
            </>
          )}
        </div>
          </>
        )}
      </div>

      {/* Tabs */}
      <div className="flex space-x-4 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('comments')}
          className={`flex items-center px-4 py-3 border-b-2 transition-colors ${
            activeTab === 'comments'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-gray-400 hover:text-white'
          }`}
        >
          <MessageSquare size={18} className="mr-2" />
          {ru.comments.title} ({comments.length})
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`flex items-center px-4 py-3 border-b-2 transition-colors ${
            activeTab === 'history'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-gray-400 hover:text-white'
          }`}
        >
          <History size={18} className="mr-2" />
          {ru.history.title} ({history.length})
        </button>
      </div>

      {/* Comments Tab */}
      {activeTab === 'comments' && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          {/* Add Comment Form */}
          <form onSubmit={handleAddComment} className="mb-6">
            <div className="flex space-x-3">
              <input
                type="text"
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder={ru.comments.placeholder}
                className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="submit"
                disabled={submitting || !newComment.trim()}
                className="flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
              >
                <Send size={16} className="mr-2" />
                {ru.comments.send}
              </button>
            </div>
          </form>

          {/* Comments List */}
          {comments.length === 0 ? (
            <p className="text-gray-400 text-center py-4">{ru.comments.noComments}</p>
          ) : (
            <div className="space-y-4">
              {comments.map((comment) => (
                <div key={comment.id} className="bg-gray-700/50 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-blue-400">
                      @{comment.user?.username || comment.user?.full_name || 'User'}
                    </span>
                    <span className="text-xs text-gray-500">{formatDate(comment.created_at)}</span>
                  </div>
                  <p className="text-gray-200">{comment.text}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          {history.length === 0 ? (
            <p className="text-gray-400 text-center py-4">{ru.common.noData}</p>
          ) : (
            <div className="space-y-3">
              {history.map((entry) => (
                <div key={entry.id} className="flex items-start space-x-3 py-2 border-b border-gray-700 last:border-0">
                  <div className="w-2 h-2 rounded-full bg-blue-500 mt-2"></div>
                  <div className="flex-1">
                    <p className="text-gray-200">
                      <span className="text-blue-400">
                        @{entry.user?.username || entry.user?.full_name || 'User'}
                      </span>
                      {' — '}
                      {historyActionLabels[entry.action] || entry.action}
                      {entry.old_value && entry.new_value && (
                        <span className="text-gray-400">
                          : {entry.old_value} → {entry.new_value}
                        </span>
                      )}
                    </p>
                    <span className="text-xs text-gray-500">{formatDate(entry.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TaskDetailPage;
