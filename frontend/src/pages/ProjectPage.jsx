import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getProject, getProjectStats, getTasks, sendReminders, addProjectMember, removeProjectMember, updateMemberRole } from '../api/client';
import { ArrowLeft, Users, CheckCircle, Clock, AlertCircle, Bell, Loader2, Crown, User as UserIcon, FileCheck, Plus, Trash2, UserPlus, ChevronDown } from 'lucide-react';
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
  const [showAddMember, setShowAddMember] = useState(false);
  const [newMemberUsername, setNewMemberUsername] = useState('');
  const [newMemberRole, setNewMemberRole] = useState('executor');
  const [addingMember, setAddingMember] = useState(false);
  const [roleDropdown, setRoleDropdown] = useState(null); // member.id of open dropdown
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

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!newMemberUsername.trim()) return;
    setAddingMember(true);
    try {
      await addProjectMember(id, { username: newMemberUsername.trim(), role: newMemberRole });
      setNewMemberUsername('');
      setNewMemberRole('executor');
      setShowAddMember(false);
      await loadProject();
    } catch (err) {
      alert(err.response?.data?.detail || 'Не удалось добавить участника');
    } finally {
      setAddingMember(false);
    }
  };

  const handleRemoveMember = async (member) => {
    const name = member.user?.username ? `@${member.user.username}` : member.user?.full_name || 'участника';
    if (!confirm(`Удалить ${name} из проекта?`)) return;
    try {
      await removeProjectMember(id, member.user_id);
      await loadProject();
    } catch (err) {
      alert(err.response?.data?.detail || 'Не удалось удалить участника');
    }
  };

  const handleChangeRole = async (member, newRole) => {
    setRoleDropdown(null);
    try {
      await updateMemberRole(id, member.user_id, { role: newRole });
      await loadProject();
    } catch (err) {
      alert(err.response?.data?.detail || 'Не удалось сменить роль');
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
            {project.description && <p className="text-gray-500">{project.description}</p>}
          </div>
        </div>
        {isManager && (
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
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white flex items-center">
            <Users size={20} className="mr-2 text-gray-400" />
            {ru.project.members} ({project.members?.length || 0})
          </h2>
          {isManager && (
            <button
              onClick={() => setShowAddMember(!showAddMember)}
              className="flex items-center px-3 py-1.5 bg-green-600/20 text-green-400 hover:bg-green-600/30 rounded-lg transition-colors text-sm"
            >
              <UserPlus size={16} className="mr-1" />
              {ru.actions.addMember}
            </button>
          )}
        </div>

        {/* Add Member Form */}
        {showAddMember && (
          <form onSubmit={handleAddMember} className="mb-4 p-4 bg-gray-700/50 rounded-lg border border-gray-600">
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <label className="block text-sm text-gray-400 mb-1">Username</label>
                <input
                  type="text"
                  value={newMemberUsername}
                  onChange={(e) => setNewMemberUsername(e.target.value)}
                  placeholder={ru.project.addMemberPlaceholder}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">{ru.role.executor}</label>
                <select
                  value={newMemberRole}
                  onChange={(e) => setNewMemberRole(e.target.value)}
                  className="px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="executor">{ru.role.executor}</option>
                  <option value="manager">{ru.role.manager}</option>
                </select>
              </div>
              <button
                type="submit"
                disabled={addingMember || !newMemberUsername.trim()}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
              >
                {addingMember ? <Loader2 size={18} className="animate-spin" /> : ru.actions.addMember}
              </button>
              <button
                type="button"
                onClick={() => { setShowAddMember(false); setNewMemberUsername(''); }}
                className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-500 transition-colors"
              >
                {ru.actions.cancel}
              </button>
            </div>
          </form>
        )}

        {/* Members List */}
        {project.members?.length > 0 ? (
          <div className="space-y-2">
            {project.members.map((member) => (
              <div
                key={member.id}
                className="flex items-center justify-between p-3 bg-gray-700/30 rounded-lg hover:bg-gray-700/50 transition-colors"
              >
                <div className="flex items-center">
                  <span className={`w-8 h-8 rounded-full flex items-center justify-center mr-3 ${getRoleColor(member.role)}`}>
                    {member.role === 'superadmin' || member.role === 'manager' ? (
                      <Crown size={16} />
                    ) : (
                      <UserIcon size={16} />
                    )}
                  </span>
                  <div>
                    <span className="text-white font-medium">
                      @{member.user?.username || member.user?.full_name || 'unknown'}
                    </span>
                    <span className={`ml-2 text-xs px-2 py-0.5 rounded ${getRoleColor(member.role)}`}>
                      {getRoleLabel(member.role)}
                    </span>
                  </div>
                </div>

                {/* Actions — only for manager+ and not for yourself (unless superadmin) */}
                {isManager && member.user_id !== user?.id && (
                  <div className="flex items-center gap-2">
                    {/* Role dropdown */}
                    <div className="relative">
                      <button
                        onClick={() => setRoleDropdown(roleDropdown === member.id ? null : member.id)}
                        className="flex items-center px-2 py-1 text-xs bg-gray-600 text-gray-300 hover:bg-gray-500 rounded transition-colors"
                      >
                        {ru.actions.changeRole}
                        <ChevronDown size={12} className="ml-1" />
                      </button>
                      {roleDropdown === member.id && (
                        <div className="absolute right-0 mt-1 bg-gray-700 border border-gray-600 rounded-lg shadow-lg z-10 min-w-[140px]">
                          {['manager', 'executor'].map((role) => (
                            <button
                              key={role}
                              onClick={() => handleChangeRole(member, role)}
                              className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-600 transition-colors first:rounded-t-lg last:rounded-b-lg ${
                                member.role === role ? 'text-blue-400' : 'text-gray-300'
                              }`}
                            >
                              {getRoleLabel(role)} {member.role === role && '✓'}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Remove button */}
                    <button
                      onClick={() => handleRemoveMember(member)}
                      className="p-1 text-red-400 hover:text-red-300 hover:bg-red-500/20 rounded transition-colors"
                      title={ru.actions.removeMember}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-400">Нет участников</p>
        )}
      </div>

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

      {/* Settings - for managers+ */}
      {isManager && project && (
        <ProjectSettings project={project} members={project.members || []} onUpdate={loadProject} />
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
