import { useState } from 'react';
import { updateProjectSettings, generateProjectToken } from '../api/client';
import { Settings, Bell, Clock, Key, Copy, Check, Loader2 } from 'lucide-react';
import { ru } from '../locales/ru';

function ProjectSettings({ project, onUpdate }) {
  const [settings, setSettings] = useState({
    reminder_enabled: project.reminder_enabled ?? true,
    reminder_time: project.reminder_time || '09:00',
  });
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateProjectSettings(project.id, settings);
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error('Failed to save settings:', err);
      alert(ru.errors.saveFailed);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateToken = async () => {
    setGenerating(true);
    try {
      await generateProjectToken(project.id);
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error('Failed to generate token:', err);
      alert(ru.errors.saveFailed);
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyLink = () => {
    const url = `${window.location.origin}/p/${project.access_token}`;
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h2 className="text-lg font-semibold text-white mb-6 flex items-center">
        <Settings size={20} className="mr-2 text-gray-400" />
        {ru.settings.title}
      </h2>

      {/* Reminders */}
      <div className="space-y-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 flex items-center">
          <Bell size={16} className="mr-2" />
          {ru.settings.reminders}
        </h3>

        <div className="flex items-center justify-between">
          <span className="text-gray-300">{ru.settings.reminderEnabled}</span>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={settings.reminder_enabled}
              onChange={(e) => setSettings({ ...settings, reminder_enabled: e.target.checked })}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
          </label>
        </div>

        {settings.reminder_enabled && (
          <div className="flex items-center justify-between">
            <span className="text-gray-300 flex items-center">
              <Clock size={14} className="mr-2" />
              {ru.settings.reminderTime}
            </span>
            <input
              type="time"
              value={settings.reminder_time}
              onChange={(e) => setSettings({ ...settings, reminder_time: e.target.value })}
              className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-1.5 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white rounded-lg transition-colors"
        >
          {saving ? (
            <Loader2 size={16} className="mr-2 animate-spin" />
          ) : (
            <Check size={16} className="mr-2" />
          )}
          {ru.actions.save}
        </button>
      </div>

      {/* Access Token */}
      <div className="space-y-4 pt-6 border-t border-gray-700">
        <h3 className="text-sm font-medium text-gray-400 flex items-center">
          <Key size={16} className="mr-2" />
          {ru.settings.accessToken}
        </h3>

        <p className="text-sm text-gray-500">{ru.settings.tokenDescription}</p>

        {project.access_token ? (
          <div className="flex items-center space-x-3">
            <code className="flex-1 bg-gray-700 px-3 py-2 rounded text-sm text-gray-300 truncate">
              {`${window.location.origin}/p/${project.access_token}`}
            </code>
            <button
              onClick={handleCopyLink}
              className="flex items-center px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition-colors"
            >
              {copied ? (
                <>
                  <Check size={16} className="mr-2 text-green-400" />
                  <span className="text-green-400">{ru.settings.linkCopied}</span>
                </>
              ) : (
                <>
                  <Copy size={16} className="mr-2" />
                  {ru.settings.copyLink}
                </>
              )}
            </button>
          </div>
        ) : (
          <button
            onClick={handleGenerateToken}
            disabled={generating}
            className="flex items-center px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition-colors"
          >
            {generating ? (
              <Loader2 size={16} className="mr-2 animate-spin" />
            ) : (
              <Key size={16} className="mr-2" />
            )}
            {ru.settings.generateToken}
          </button>
        )}
      </div>
    </div>
  );
}

export default ProjectSettings;
