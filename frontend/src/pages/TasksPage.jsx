import { useState, useEffect } from 'react';
import { getTasks, getProjects } from '../api/client';
import { Filter, RefreshCw } from 'lucide-react';
import TaskCard from '../components/TaskCard';
import { useAuth } from '../context/AuthContext';
import { ru } from '../locales/ru';

function TasksPage() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    project_id: '',
    status: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    loadTasks();
  }, [filters]);

  const loadData = async () => {
    try {
      const projectsRes = await getProjects();
      setProjects(projectsRes.data);
    } catch (err) {
      console.error('Failed to load projects:', err);
    }
  };

  const loadTasks = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.project_id) params.project_id = filters.project_id;
      if (filters.status) params.status = filters.status;

      const response = await getTasks(params);
      setTasks(response.data);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">{ru.tasksPage.title}</h1>

      {/* Filters */}
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <div className="flex flex-wrap items-center gap-4">
          <Filter size={20} className="text-gray-400" />
          <select
            value={filters.project_id}
            onChange={(e) => setFilters({ ...filters, project_id: e.target.value })}
            className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">{ru.tasksPage.allProjects}</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>

          <select
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">{ru.status.all}</option>
            <option value="pending">{ru.status.pending}</option>
            <option value="in_progress">{ru.status.in_progress}</option>
            <option value="pending_review">{ru.status.pending_review}</option>
            <option value="done">{ru.status.done}</option>
          </select>

          <button
            onClick={() => setFilters({ project_id: '', status: '' })}
            className="flex items-center text-gray-400 hover:text-white text-sm transition-colors"
          >
            <RefreshCw size={14} className="mr-1" />
            {ru.actions.reset}
          </button>
        </div>
      </div>

      {/* Tasks List */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
          </div>
        ) : tasks.length === 0 ? (
          <p className="text-gray-400 text-center py-8">
            {ru.tasksPage.noTasksFound}
          </p>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => (
              <TaskCard key={task.id} task={task} onUpdate={loadTasks} isManager={user?.is_superadmin} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default TasksPage;
