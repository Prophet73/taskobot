import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getDashboard, sendReminders } from '../api/client';
import { CheckCircle, Clock, AlertCircle, Users, TrendingUp, Bell, Loader2 } from 'lucide-react';
import TaskCard from '../components/TaskCard';
import StatsCard from '../components/StatsCard';
import { useAuth } from '../context/AuthContext';
import { ru } from '../locales/ru';

function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sendingReminder, setSendingReminder] = useState(null);
  const { user } = useAuth();

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const response = await getDashboard();
      setData(response.data);
    } catch (err) {
      setError(ru.errors.loadFailed);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSendReminders = async (projectId, e) => {
    e.preventDefault();
    e.stopPropagation();
    setSendingReminder(projectId);
    try {
      const response = await sendReminders(projectId);
      alert(`Sent to ${response.data.sent_count} users`);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to send reminders');
    } finally {
      setSendingReminder(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/20 border border-red-500 text-red-400 px-4 py-3 rounded-lg">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h1 className="text-2xl font-bold text-white">
          {ru.dashboard.welcome}, {user?.full_name || user?.username || 'User'}!
        </h1>
        <p className="text-gray-400 mt-1">
          {user?.is_superadmin ? 'Полный доступ ко всем проектам' : 'Ваши проекты'}
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatsCard
          title={ru.dashboard.totalTasks}
          value={data?.total_tasks || 0}
          icon={AlertCircle}
          color="blue"
        />
        <StatsCard
          title={ru.dashboard.completed}
          value={data?.total_completed || 0}
          icon={CheckCircle}
          color="green"
        />
        <StatsCard
          title={ru.dashboard.projects}
          value={data?.projects?.length || 0}
          icon={Users}
          color="purple"
        />
        <StatsCard
          title={ru.dashboard.completionRate}
          value={`${(data?.completion_rate || 0).toFixed(1)}%`}
          icon={TrendingUp}
          color="orange"
        />
      </div>

      {/* Projects */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-4">{ru.dashboard.projects}</h2>
        {data?.projects?.length === 0 ? (
          <p className="text-gray-400">
            {ru.dashboard.noProjects}
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data?.projects?.map((project) => (
              <Link
                key={project.project_id}
                to={`/projects/${project.project_id}`}
                className="block p-4 bg-gray-700/50 border border-gray-600 rounded-lg hover:border-blue-500 transition-colors group"
              >
                <div className="flex justify-between items-start">
                  <h3 className="font-medium text-lg text-white group-hover:text-blue-400 transition-colors">
                    {project.project_name}
                  </h3>
                  {/* Reminder button for managers */}
                  {user?.is_superadmin && (
                    <button
                      onClick={(e) => handleSendReminders(project.project_id, e)}
                      disabled={sendingReminder === project.project_id}
                      className="p-2 text-gray-400 hover:text-yellow-400 hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50"
                      title={ru.actions.sendReminders}
                    >
                      {sendingReminder === project.project_id ? (
                        <Loader2 size={18} className="animate-spin" />
                      ) : (
                        <Bell size={18} />
                      )}
                    </button>
                  )}
                </div>
                <div className="mt-3 flex space-x-4 text-sm text-gray-400">
                  <span className="flex items-center">
                    <Clock size={14} className="mr-1" />
                    {project.pending_tasks} ожидает
                  </span>
                  <span className="flex items-center">
                    <CheckCircle size={14} className="mr-1" />
                    {project.completed_tasks} выполнено
                  </span>
                </div>
                <div className="mt-3">
                  <div className="bg-gray-600 rounded-full h-2">
                    <div
                      className="bg-green-500 rounded-full h-2 transition-all"
                      style={{
                        width: `${
                          project.total_tasks > 0
                            ? (project.completed_tasks / project.total_tasks) * 100
                            : 0
                        }%`,
                      }}
                    ></div>
                  </div>
                </div>
                <div className="mt-2 text-xs text-gray-500">
                  {project.members_count} участников
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Recent Tasks */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-4">{ru.dashboard.recentTasks}</h2>
        {data?.recent_tasks?.length === 0 ? (
          <p className="text-gray-400">{ru.dashboard.noTasks}</p>
        ) : (
          <div className="space-y-3">
            {data?.recent_tasks?.map((task) => (
              <TaskCard key={task.id} task={task} onUpdate={loadDashboard} isManager={user?.is_superadmin} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
