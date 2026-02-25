import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getProject, getProjectStats, getTasks, sendReminders } from '../api/client';
import { ArrowLeft, Users, CheckCircle, Clock, AlertCircle, Bell, Loader2, Crown, User as UserIcon, FileCheck, Plus } from 'lucide-react';
import TaskCard from '../components/TaskCard';
import StatsCard from '../components/StatsCard';
import ProjectSettings from '../components/ProjectSettings';
import CreateTaskModal from '../components/CreateTaskModal';
import { useAuth } from '../context/AuthContext';
import { ru } from '../locales/ru';

function ProjectPage() {
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [stats, setStats] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [sendingReminder, setSendingReminder] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const { user } = useAuth();

  useEffect(() => {
    loadProject();
  }, [id]);

  const loadProject = async () => {
    try {
      const [projectRes, statsRes, tasksRes] = await Promise.all([
        getProject(id),
        getProjectStats(id),
        getTasks({ project_id: id }),
      ]);
      setProject(projectRes.data);
      setStats(statsRes.data);
      setTasks(tasksRes.data);
    } catch (err) {
      console.error('Failed to load project:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSendReminders = async () => {
    setSendingReminder(true);
    try {
      const response = await sendReminders(parseInt(id));
      alert(`Sent to ${response.data.sent_count} users`);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to send reminders');
    } finally {
      setSendingReminder(false);
    }
  };

  const filteredTasks = tasks.filter((task) => {
    if (filter === 'all') return true;
    return task.status === filter;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-400">{ru.project.notFound}</p>
        <Link to="/" className="text-blue-400 hover:underline mt-2 inline-block">
          {ru.project.backToDashboard}
        </Link>
      </div>
    );
  }

  // Определяем, является ли текущий пользователь менеджером
  const isManager = user?.is_superadmin ||
    project.members?.some(m => m.user_id === user?.id && (m.role === 'manager' || m.role === 'superadmin'));

  const getRoleLabel = (role) => {
    switch (role) {
      case 'superadmin': return ru.role.superadmin;
      case 'manager': return ru.role.manager;
      case 'executor': return ru.role.executor;
      default: return role;
    }
  };

  const getRoleColor = (role) => {
    switch (role) {
      case 'superadmin': return 'bg-yellow-500/20 text-yellow-400';
      case 'manager': return 'bg-blue-500/20 text-blue-400';
      default: return 'bg-gray-500/20 text-gray-400';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link to="/" className="text-gray-400 hover:text-white transition-colors">
            <ArrowLeft size={24} />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-white">{project.name}</h1>
            <p className="text-gray-500">Chat ID: {project.chat_id}</p>
          </div>
        </div>
        {user?.is_superadmin && (
          <button
            onClick={handleSendReminders}
            disabled={sendingReminder}
            className="flex items-center px-4 py-2 bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 rounded-lg transition-colors disabled:opacity-50"
          >
            {sendingReminder ? (
              <Loader2 size={18} className="mr-2 animate-spin" />
            ) : (
              <Bell size={18} className="mr-2" />
            )}
            {ru.actions.sendReminders}
          </button>
        )}
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatsCard
            title={ru.dashboard.totalTasks}
            value={stats.total_tasks}
            icon={AlertCircle}
            color="blue"
          />
          <StatsCard
            title={ru.status.pending}
            value={stats.pending_tasks}
            icon={Clock}
            color="orange"
          />
          <StatsCard
            title={ru.status.in_progress}
            value={stats.in_progress_tasks}
            icon={AlertCircle}
            color="purple"
          />
          <StatsCard
            title={ru.dashboard.completed}
            value={stats.completed_tasks}
            icon={CheckCircle}
            color="green"
          />
        </div>
      )}

      {/* Members */}
      {project.members?.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center">
            <Users size={20} className="mr-2 text-gray-400" />
            {ru.project.members} ({project.members.length})
          </h2>
          <div className="flex flex-wrap gap-2">
            {project.members.map((member) => (
              <span
                key={member.id}
                className={`px-3 py-1.5 rounded-lg text-sm flex items-center ${getRoleColor(member.role)}`}
              >
                {member.role === 'superadmin' || member.role === 'manager' ? (
                  <Crown size={14} className="mr-1" />
                ) : (
                  <UserIcon size={14} className="mr-1" />
                )}
                @{member.user?.username || member.user?.full_name || 'unknown'}
                <span className="ml-1 opacity-70">({getRoleLabel(member.role)})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tasks */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-3">
            <h2 className="text-lg font-semibold text-white">{ru.project.tasks}</h2>
            {isManager && (
              <button
                onClick={() => setShowCreateModal(true)}
                className="flex items-center px-3 py-1.5 bg-green-600/20 text-green-400 hover:bg-green-600/30 rounded-lg transition-colors text-sm"
                title={ru.actions.createTask}
              >
                <Plus size={16} className="mr-1" />
                {ru.actions.createTask}
              </button>
            )}
          </div>
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
              <TaskCard key={task.id} task={task} onUpdate={loadProject} isManager={isManager} />
            ))}
          </div>
        )}
      </div>

      {/* Settings - only for superadmins */}
      {user?.is_superadmin && project && (
        <ProjectSettings project={project} onUpdate={loadProject} />
      )}

      {/* Create Task Modal */}
      {showCreateModal && (
        <CreateTaskModal
          projectId={id}
          onClose={() => setShowCreateModal(false)}
          onCreated={loadProject}
        />
      )}
    </div>
  );
}

export default ProjectPage;
