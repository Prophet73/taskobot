import { useState } from 'react';
import { Link } from 'react-router-dom';
import { updateTask } from '../api/client';
import { Check, Clock, AlertTriangle, User, Play, FileCheck, MessageSquare, RotateCcw } from 'lucide-react';
import { ru } from '../locales/ru';

const statusConfig = {
  pending: { label: ru.status.pending, color: 'bg-yellow-500/20 text-yellow-400', icon: Clock },
  in_progress: { label: ru.status.in_progress, color: 'bg-blue-500/20 text-blue-400', icon: AlertTriangle },
  pending_review: { label: ru.status.pending_review, color: 'bg-purple-500/20 text-purple-400', icon: FileCheck },
  done: { label: ru.status.done, color: 'bg-green-500/20 text-green-400', icon: Check },
  cancelled: { label: ru.status.cancelled, color: 'bg-gray-500/20 text-gray-400', icon: null },
};

const priorityConfig = {
  urgent: { label: ru.priority.urgent, color: 'bg-red-500' },
  high: { label: ru.priority.high, color: 'bg-orange-500' },
  normal: { label: ru.priority.normal, color: 'bg-green-500' },
  low: { label: ru.priority.low, color: 'bg-gray-500' },
};

function TaskCard({ task, onUpdate, isManager = false, readOnly = false }) {
  const [updating, setUpdating] = useState(false);

  const handleStatusChange = async (newStatus) => {
    setUpdating(true);
    try {
      await updateTask(task.id, { status: newStatus });
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error('Failed to update task:', err);
    } finally {
      setUpdating(false);
    }
  };

  const status = statusConfig[task.status] || statusConfig.pending;
  const priority = priorityConfig[task.priority] || priorityConfig.normal;

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'short',
    });
  };

  return (
    <div className={`bg-gray-700/50 border border-gray-600 rounded-lg p-4 hover:border-gray-500 transition-all ${task.status === 'done' ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {/* Priority indicator */}
          <div className="flex items-center space-x-2 mb-2">
            <span className={`w-2 h-2 rounded-full ${priority.color}`}></span>
            <Link to={`/tasks/${task.id}`} className="text-xs text-gray-500 hover:text-blue-400 transition-colors">
              #{task.id}
            </Link>
            <span className={`text-xs px-2 py-0.5 rounded ${status.color}`}>
              {status.label}
            </span>
          </div>

          {/* Description */}
          <p className={`text-gray-200 ${task.status === 'done' ? 'line-through text-gray-500' : ''}`}>
            {task.description}
          </p>

          {/* Meta info */}
          <div className="flex items-center space-x-4 mt-2 text-sm text-gray-500">
            {task.assignee && (
              <span className="flex items-center">
                <User size={14} className="mr-1" />
                @{task.assignee.username || task.assignee.full_name}
              </span>
            )}
            <span>{formatDate(task.created_at)}</span>
            <Link
              to={`/tasks/${task.id}`}
              className="flex items-center text-gray-500 hover:text-blue-400 transition-colors"
            >
              <MessageSquare size={14} className="mr-1" />
              {ru.actions.comment}
            </Link>
          </div>
        </div>

        {/* Actions */}
        {!readOnly && task.status !== 'done' && (
          <div className="flex space-x-2 ml-4">
            {task.status === 'pending' && (
              <button
                onClick={() => handleStatusChange('in_progress')}
                disabled={updating}
                className="flex items-center px-3 py-1.5 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 rounded-lg text-sm transition-colors disabled:opacity-50"
              >
                <Play size={14} className="mr-1" />
                {ru.actions.start}
              </button>
            )}
            {task.status === 'in_progress' && (
              <button
                onClick={() => handleStatusChange('pending_review')}
                disabled={updating}
                className="flex items-center px-3 py-1.5 bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 rounded-lg text-sm transition-colors disabled:opacity-50"
              >
                <FileCheck size={14} className="mr-1" />
                {ru.actions.toReview}
              </button>
            )}
            {task.status === 'pending_review' && isManager && (
              <>
                <button
                  onClick={() => handleStatusChange('done')}
                  disabled={updating}
                  className="flex items-center px-3 py-1.5 bg-green-600/20 text-green-400 hover:bg-green-600/30 rounded-lg text-sm transition-colors disabled:opacity-50"
                >
                  <Check size={14} className="mr-1" />
                  {ru.actions.approve}
                </button>
                <button
                  onClick={() => handleStatusChange('in_progress')}
                  disabled={updating}
                  className="flex items-center px-3 py-1.5 bg-orange-600/20 text-orange-400 hover:bg-orange-600/30 rounded-lg text-sm transition-colors disabled:opacity-50"
                >
                  <RotateCcw size={14} className="mr-1" />
                  {ru.actions.reject}
                </button>
              </>
            )}
            {task.status === 'pending_review' && !isManager && (
              <span className="text-xs text-purple-400 bg-purple-500/20 px-2 py-1 rounded">
                {ru.task.waitingReview}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default TaskCard;
