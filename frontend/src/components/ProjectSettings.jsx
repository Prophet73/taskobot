import { useState, useEffect } from 'react';
import { updateProjectSettings, createProjectToken, getProjectTokens, revokeProjectToken } from '../api/client';
import { Settings, Bell, Clock, Key, Copy, Check, Loader2, Trash2, Eye, Hammer, Shield, RefreshCw, User } from 'lucide-react';
import { ru } from '../locales/ru';

function TokenRow({ t, copiedToken, revokingId, onCopy, onRevoke }) {
  return (
    <div className="flex items-center space-x-2">
      {t.member && (
        <span className="flex items-center text-xs text-gray-400 min-w-0 shrink-0">
          <User size={12} className="mr-1" />
          @{t.member.username || t.member.full_name}
        </span>
      )}
      <code className="flex-1 bg-gray-700 px-3 py-1.5 rounded text-xs text-gray-300 truncate">
        {`${window.location.origin}/p/${t.token}`}
      </code>
      <button
        onClick={() => onCopy(t.token)}
        className="flex items-center px-2 py-1.5 bg-gray-600 hover:bg-gray-500 text-gray-300 rounded text-xs transition-colors shrink-0"
      >
        {copiedToken === t.token ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
      </button>
      <button
        onClick={() => onRevoke(t.id)}
        disabled={revokingId === t.id}
        className="flex items-center px-2 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded text-xs transition-colors disabled:opacity-50 shrink-0"
      >
        {revokingId === t.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
      </button>
    </div>
  );
}

function ProjectSettings({ project, members = [], onUpdate }) {
  const [settings, setSettings] = useState({
    reminder_enabled: project.reminder_enabled ?? true,
    reminder_time: project.reminder_time || '09:00',
  });
  const [saving, setSaving] = useState(false);
  const [tokens, setTokens] = useState([]);
  const [loadingTokens, setLoadingTokens] = useState(true);
  const [generatingRole, setGeneratingRole] = useState(null);
  const [copiedToken, setCopiedToken] = useState(null);
  const [revokingId, setRevokingId] = useState(null);

  useEffect(() => {
    loadTokens();
  }, [project.id]);

  const loadTokens = async () => {
    try {
      const res = await getProjectTokens(project.id);
      setTokens(res.data);
    } catch (err) {
      console.error('Failed to load tokens:', err);
    } finally {
      setLoadingTokens(false);
    }
  };

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

  const handleGenerateToken = async (role, memberId = null) => {
    setGeneratingRole(memberId ? `executor-${memberId}` : role);
    try {
      await createProjectToken(project.id, role, memberId);
      await loadTokens();
    } catch (err) {
      console.error('Failed to generate token:', err);
      alert(ru.errors.saveFailed);
    } finally {
      setGeneratingRole(null);
    }
  };

  const handleRevokeToken = async (tokenId) => {
    if (!confirm(ru.settings.revokeConfirm)) return;
    setRevokingId(tokenId);
    try {
      await revokeProjectToken(project.id, tokenId);
      await loadTokens();
    } catch (err) {
      console.error('Failed to revoke token:', err);
      alert(ru.errors.saveFailed);
    } finally {
      setRevokingId(null);
    }
  };

  const handleCopyLink = (token) => {
    const url = `${window.location.origin}/p/${token}`;
    navigator.clipboard.writeText(url);
    setCopiedToken(token);
    setTimeout(() => setCopiedToken(null), 2000);
  };

  const observerToken = tokens.find((t) => t.role === 'observer');
  const managerToken = tokens.find((t) => t.role === 'manager');
  const executorTokens = tokens.filter((t) => t.role === 'executor');

  // Участники, у которых ещё нет executor-токена
  const memberUsers = members.map((m) => m.user).filter(Boolean);
  const membersWithTokens = new Set(executorTokens.map((t) => t.member_id));

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
          {saving ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Check size={16} className="mr-2" />}
          {ru.actions.save}
        </button>
      </div>

      {/* Access Tokens */}
      <div className="space-y-4 pt-6 border-t border-gray-700">
        <h3 className="text-sm font-medium text-gray-400 flex items-center">
          <Key size={16} className="mr-2" />
          {ru.settings.accessTokens}
        </h3>
        <p className="text-sm text-gray-500">{ru.settings.tokensDescription}</p>

        {loadingTokens ? (
          <div className="flex items-center text-gray-500">
            <Loader2 size={16} className="mr-2 animate-spin" />
            {ru.common.loading}
          </div>
        ) : (
          <div className="space-y-4">

            {/* Observer — один токен */}
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center">
                  <Eye size={16} className="mr-2 text-blue-400" />
                  <span className="text-white font-medium">{ru.tokenRole.observer}</span>
                </div>
                <button
                  onClick={() => handleGenerateToken('observer')}
                  disabled={generatingRole === 'observer'}
                  className="flex items-center px-3 py-1.5 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 rounded-lg text-sm transition-colors disabled:opacity-50"
                >
                  {generatingRole === 'observer' ? (
                    <Loader2 size={14} className="mr-1 animate-spin" />
                  ) : observerToken ? (
                    <RefreshCw size={14} className="mr-1" />
                  ) : (
                    <Key size={14} className="mr-1" />
                  )}
                  {observerToken ? ru.settings.regenerateToken : ru.settings.generateToken}
                </button>
              </div>
              <p className="text-xs text-gray-400 mb-3">{ru.tokenRole.observerDesc}</p>
              {observerToken ? (
                <TokenRow t={observerToken} copiedToken={copiedToken} revokingId={revokingId} onCopy={handleCopyLink} onRevoke={handleRevokeToken} />
              ) : (
                <p className="text-xs text-gray-500">{ru.settings.noTokens}</p>
              )}
            </div>

            {/* Executor — токен на каждого участника */}
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="flex items-center mb-2">
                <Hammer size={16} className="mr-2 text-purple-400" />
                <span className="text-white font-medium">{ru.tokenRole.executor}</span>
              </div>
              <p className="text-xs text-gray-400 mb-3">{ru.tokenRole.executorDesc}</p>

              {memberUsers.length === 0 ? (
                <p className="text-xs text-gray-500">{ru.settings.noTokens}</p>
              ) : (
                <div className="space-y-3">
                  {memberUsers.map((user) => {
                    const existingToken = executorTokens.find((t) => t.member_id === user.id);
                    const genKey = `executor-${user.id}`;
                    return (
                      <div key={user.id} className="border-t border-gray-600 pt-2 first:border-0 first:pt-0">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-sm text-gray-300 flex items-center">
                            <User size={14} className="mr-1.5 text-gray-500" />
                            @{user.username || user.full_name || 'unknown'}
                          </span>
                          <button
                            onClick={() => handleGenerateToken('executor', user.id)}
                            disabled={generatingRole === genKey}
                            className="flex items-center px-2 py-1 bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 rounded text-xs transition-colors disabled:opacity-50"
                          >
                            {generatingRole === genKey ? (
                              <Loader2 size={12} className="mr-1 animate-spin" />
                            ) : existingToken ? (
                              <RefreshCw size={12} className="mr-1" />
                            ) : (
                              <Key size={12} className="mr-1" />
                            )}
                            {existingToken ? ru.settings.regenerateToken : ru.settings.generateToken}
                          </button>
                        </div>
                        {existingToken && (
                          <TokenRow t={existingToken} copiedToken={copiedToken} revokingId={revokingId} onCopy={handleCopyLink} onRevoke={handleRevokeToken} />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Manager — один токен */}
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center">
                  <Shield size={16} className="mr-2 text-orange-400" />
                  <span className="text-white font-medium">{ru.tokenRole.manager}</span>
                </div>
                <button
                  onClick={() => handleGenerateToken('manager')}
                  disabled={generatingRole === 'manager'}
                  className="flex items-center px-3 py-1.5 bg-orange-600/20 text-orange-400 hover:bg-orange-600/30 rounded-lg text-sm transition-colors disabled:opacity-50"
                >
                  {generatingRole === 'manager' ? (
                    <Loader2 size={14} className="mr-1 animate-spin" />
                  ) : managerToken ? (
                    <RefreshCw size={14} className="mr-1" />
                  ) : (
                    <Key size={14} className="mr-1" />
                  )}
                  {managerToken ? ru.settings.regenerateToken : ru.settings.generateToken}
                </button>
              </div>
              <p className="text-xs text-gray-400 mb-3">{ru.tokenRole.managerDesc}</p>
              {managerToken ? (
                <TokenRow t={managerToken} copiedToken={copiedToken} revokingId={revokingId} onCopy={handleCopyLink} onRevoke={handleRevokeToken} />
              ) : (
                <p className="text-xs text-gray-500">{ru.settings.noTokens}</p>
              )}
            </div>

          </div>
        )}
      </div>
    </div>
  );
}

export default ProjectSettings;
