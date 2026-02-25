import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, FolderKanban, ListTodo, LogOut, User, Crown } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { ru } from '../locales/ru';

const navItems = [
  { path: '/', label: ru.nav.dashboard, icon: LayoutDashboard },
  { path: '/tasks', label: ru.nav.tasks, icon: ListTodo },
];

function Layout({ children }) {
  const location = useLocation();
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Header */}
      <header className="bg-gray-800 text-white shadow-lg border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center space-x-3">
              <FolderKanban size={28} className="text-blue-400" />
              <h1 className="text-xl font-bold">Трекер задач</h1>
            </Link>

            <div className="flex items-center space-x-6">
              <nav className="flex space-x-2">
                {navItems.map((item) => (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`flex items-center space-x-2 px-3 py-2 rounded-lg transition-colors ${
                      location.pathname === item.path
                        ? 'bg-blue-600 text-white'
                        : 'text-gray-300 hover:bg-gray-700'
                    }`}
                  >
                    <item.icon size={18} />
                    <span className="hidden sm:inline">{item.label}</span>
                  </Link>
                ))}
              </nav>

              {/* User info */}
              <div className="flex items-center space-x-3 border-l border-gray-600 pl-4">
                <div className="flex items-center space-x-2">
                  {user?.is_superadmin ? (
                    <Crown size={18} className="text-yellow-400" />
                  ) : (
                    <User size={18} className="text-gray-400" />
                  )}
                  <span className="text-sm text-gray-300">
                    {user?.username ? `@${user.username}` : user?.full_name || 'User'}
                  </span>
                </div>
                <button
                  onClick={logout}
                  className="p-2 text-gray-400 hover:text-red-400 transition-colors"
                  title="Logout"
                >
                  <LogOut size={18} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        {children}
      </main>
    </div>
  );
}

export default Layout;
