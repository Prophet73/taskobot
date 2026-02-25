import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getProjectByToken, updateTaskByToken } from '../api/client';
import { FolderKanban, Users, CheckCircle, Clock, AlertCircle, Plus, Eye, Hammer, Shield } from 'lucide-react';
import TaskCard from '../components/TaskCard';
import StatsCard from '../components/StatsCard';
import { ru } from '../locales/ru';

const roleBadge = {
  observer: { label: ru.tokenRole.observer, icon: Eye, color: 'bg-blue-600/20 text-blue-400' },
  executor: { label: ru.tokenRole.executor, icon: Hammer, color: 'bg-purple-600/20 text-purple-400' },
  manager: { label: ru.tokenRole.manager, icon: Shield, color: 'bg-orange-600/20 text-orange-400' },
};

function TokenProjectPage() {
  const { token } = useParams();
  const [project, setProject] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [members, setMembers] = useState([]);
  const [stats, setStats] = useState(null);
  const [tokenRole, setTokenRole] = useState('observer');
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Create task form (manager only)
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTask, setNewTask] = useState({ description: '', assignee_id: '', priority: 'normal' });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadProject();
  }, [token]);

  const loadProject = async () => {
    try {
      const res = await getProjectByToken(token);
      setProject(res.data.project);
      setTasks(res.data.tasks || []);
      setStats(res.data.stats);
      setTokenRole(res.data.token_role || 'observer');
      setMembers(res.data.members || []);
    } catch (err) {
      console.error('Failed to load project:', err);
      setError(ru.errors.accessDenied);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    if (!newTask.description.trim() || !newTask.assignee_id) return;
    setCreating(true);
    try {
      await updateTaskByToken(token, 0, {
        // This won't work via token-tasks endpoint - manager creates via a different mechanism
        // For now, we use a dedicated approach
      });
    } catch (err) {
      // Task creation via token is not supported in current backend
      // This would need a separate endpoint
      console.error('Create task not available via token');
    } finally {
      setCreating(false);
    }
  };

  const isReadOnly = tokenRole === 'observer';
  const isManager = tokenRole === 'manager';
  const isExecutor = tokenRole === 'executor';

  const filteredTasks = tasks.filter((task) => {
    if (filter === 'all') return true;
    return task.status === filter;
  });

  const localStats = stats || {
    total_tasks: tasks.length,
    pending_tasks: tasks.filter(t => t.status === 'pending').length,
    in_progress_tasks: tasks.filter(t => t.status === 'in_progress').length,
    pending_review_tasks: tasks.filter(t => t.status === 'pending_review').length,
    completed_tasks: tasks.filter(t => t.status === 'done').length,
  };

  const badge = roleBadge[tokenRole] || roleBadge.observer;
  const BadgeIcon = badge.icon;

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
        <div className="text-center">
          <FolderKanban size={48} className="mx-auto text-gray-600 mb-4" />
          <h1 className="text-xl font-bold text-white mb-2">{ru.errors.accessDenied}</h1>
          <p className="text-gray-400">{ru.project.notFound}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Header */}
      <header className="bg-gray-800 text-white shadow-lg border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <FolderKanban size={28} className="text-blue-400" />
              <div>
                <h1 className="text-xl font-bold">{project?.name}</h1>
                <p className="text-sm text-gray-400">{ru.dashboard.title}</p>
              </div>
            </div>
            <span className={`flex items-center px-3 py-1.5 rounded-lg text-sm ${badge.color}`}>
              <BadgeIcon size={14} className="mr-1.5" />
              {badge.label}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatsCard
            title={ru.dashboard.totalTasks}
            value={localStats.total_tasks}
            icon={AlertCircle}
            color="blue"
          />
          <StatsCard
            title={ru.status.pending}
            value={localStats.pending_tasks}
            icon={Clock}
            color="yellow"
          />
          <StatsCard
            title={ru.status.in_progress}
            value={localStats.in_progress_tasks}
            icon={AlertCircle}
            color="purple"
          />
          <StatsCard
            title={ru.status.pending_review}
            value={localStats.pending_review_tasks}
            icon={AlertCircle}
            color="orange"
          />
          <StatsCard
            title={ru.dashboard.completed}
            value={localStats.completed_tasks}
            icon={CheckCircle}
            color="green"
          />
        </div>

        {/* Members */}
        {members.length > 0 && (
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center">
              <Users size={20} className="mr-2 text-gray-400" />
              {ru.project.members} ({members.length})
            </h2>
            <div className="flex flex-wrap gap-2">
              {members.map((member) => (
                <span
                  key={member.id}
                  className="px-3 py-1.5 rounded-lg text-sm bg-gray-700 text-gray-300"
                >
                  @{member.user?.username || member.user?.full_name || 'unknown'}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Tasks */}
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">{ru.project.tasks}</h2>
            <div className="flex space-x-2 flex-wrap gap-1">
              {['all', 'pending', 'in_progress', 'pending_review', 'done'].map((status) => (
                <button
                  key={status}
                  onClick={() => setFilter(status)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    filter === status
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {status === 'all' && ru.project.allTasks}
                  {status === 'pending' && ru.status.pending}
                  {status === 'in_progress' && ru.status.in_progress}
                  {status === 'pending_review' && ru.status.pending_review}
                  {status === 'done' && ru.status.done}
                </button>
              ))}
            </div>
          </div>

          {filteredTasks.length === 0 ? (
            <p className="text-gray-400">{ru.dashboard.noTasks}</p>
          ) : (
            <div className="space-y-3">
              {filteredTasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onUpdate={loadProject}
                  readOnly={isReadOnly}
                  isManager={isManager}
                  tokenAuth={isReadOnly ? null : token}
                />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default TokenProjectPage;
