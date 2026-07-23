import { useState, useEffect, useRef } from 'react';
import {
  Music,
  FolderSearch,
  Play,
  Square,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  FileAudio,
  Radio,
  ListMusic,
  RefreshCw,
} from 'lucide-react';
import type { TaskItem, ProgressMessage } from './types';

export function App() {
  const [scanPath, setScanPath] = useState<string>('');
  const [recursive, setRecursive] = useState<boolean>(false);
  const [enrichNetease, setEnrichNetease] = useState<boolean>(true);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [logMessages, setLogMessages] = useState<string[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  // Stats calculation
  const totalCount = tasks.length;
  const successCount = tasks.filter((t) => t.status === 'success').length;
  const failedCount = tasks.filter((t) => t.status === 'failed').length;
  const overallProgress =
    totalCount > 0
      ? Math.round(
          (tasks.reduce((acc, curr) => acc + curr.progress, 0) / (totalCount * 100)) * 100
        )
      : 0;

  const getApiBase = () => {
    return window.location.port === '5173' ? 'http://127.0.0.1:8000' : '';
  };

  // Initialize WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.port === '5173' ? '127.0.0.1:8000' : (window.location.host || '127.0.0.1:8000');
    const wsUrl = `${protocol}//${host}/api/ws/progress`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket Connected to Backend:', wsUrl);
    };

    ws.onmessage = (event) => {
      try {
        const msg: ProgressMessage = JSON.parse(event.data);
        if (msg.event === 'batch_start') {
          setIsProcessing(true);
        } else if (msg.event === 'batch_complete') {
          setIsProcessing(false);
        } else if (msg.event === 'item_update' && msg.item) {
          const updatedItem = msg.item;
          setTasks((prev) => {
            const index = prev.findIndex((t) => t.id === updatedItem.id);
            if (index !== -1) {
              const next = [...prev];
              next[index] = { ...next[index], ...updatedItem };
              return next;
            } else {
              return [...prev, updatedItem];
            }
          });
        }

        if (msg.message) {
          setLogMessages((prev) => [msg.message!, ...prev.slice(0, 49)]);
        }
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket Disconnected');
    };

    return () => {
      ws.close();
    };
  }, []);

  // Initial auto scan on mount
  useEffect(() => {
    handleScan();
  }, []);

  const handleScan = async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paths: scanPath.trim() ? [scanPath.trim()] : [],
          recursive: recursive,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setTasks(data.items || []);
      }
    } catch (err) {
      console.error('Scan error:', err);
    }
  };

  const handleStartBatch = async () => {
    if (isProcessing) return;
    try {
      const res = await fetch(`${getApiBase()}/api/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paths: scanPath.trim() ? [scanPath.trim()] : [],
          enrich_netease: enrichNetease,
          recursive: recursive,
        }),
      });
      if (res.ok) {
        setIsProcessing(true);
      }
    } catch (err) {
      console.error('Start batch error:', err);
    }
  };

  const handleCancelBatch = async () => {
    try {
      await fetch(`${getApiBase()}/api/cancel`, { method: 'POST' });
      setIsProcessing(false);
    } catch (err) {
      console.error('Cancel batch error:', err);
    }
  };

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '32px 20px' }}>
      {/* Header Bar */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '24px',
          background: '#ffffff',
          padding: '20px 24px',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '10px',
              background: '#0284c7',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
            }}
          >
            <Music size={22} />
          </div>
          <div>
            <h1 style={{ fontSize: '20px', fontWeight: 600, color: '#0f172a' }}>
              NCM 音频转换 & 网易云元数据提取器
            </h1>
            <p style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>
              高效解密 NCM 音频，自动补全官方高保真元数据、多歌手与原画封面
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            onClick={handleScan}
            disabled={isProcessing}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '9px 16px',
              fontSize: '14px',
              fontWeight: 500,
              color: '#334155',
              background: '#f1f5f9',
              borderRadius: '8px',
              cursor: isProcessing ? 'not-allowed' : 'pointer',
            }}
          >
            <RefreshCw size={16} /> 刷新扫描
          </button>
        </div>
      </header>

      {/* Control Panel */}
      <div
        style={{
          background: '#ffffff',
          borderRadius: '12px',
          padding: '20px 24px',
          marginBottom: '24px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        {/* Search Path Input */}
        <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <input
              type="text"
              placeholder="请输入 NCM / 音频文件或扫描文件夹路径（留空则默认为当前项目目录）"
              value={scanPath}
              onChange={(e) => setScanPath(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 14px 10px 38px',
                fontSize: '14px',
                border: '1px solid #cbd5e1',
                borderRadius: '8px',
                background: '#ffffff',
                color: '#1e293b',
              }}
            />
            <FolderSearch
              size={18}
              style={{
                position: 'absolute',
                left: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: '#94a3b8',
              }}
            />
          </div>
          <button
            onClick={handleScan}
            disabled={isProcessing}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              fontWeight: 500,
              color: '#ffffff',
              background: '#0284c7',
              borderRadius: '8px',
              opacity: isProcessing ? 0.6 : 1,
            }}
          >
            扫描路径
          </button>
        </div>

        {/* Option Selectors */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingTop: '12px',
            borderTop: '1px solid #f1f5f9',
          }}
        >
          <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '14px',
                color: '#0f172a',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              <Sparkles size={16} color="#0284c7" />
              <span>
                数据来源: <strong>默认从网易云补充高保真元数据 & 原画封面</strong>
              </span>
            </label>

            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13px',
                color: '#64748b',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={!enrichNetease}
                onChange={(e) => setEnrichNetease(!e.target.checked)}
                style={{ width: '15px', height: '15px', accentColor: '#0284c7' }}
              />
              纯离线模式 (仅本地解密 NCM)
            </label>

            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13px',
                color: '#64748b',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={recursive}
                onChange={(e) => setRecursive(e.target.checked)}
                style={{ width: '15px', height: '15px', accentColor: '#0284c7' }}
              />
              递归扫描子目录
            </label>
          </div>

          <div>
            {!isProcessing ? (
              <button
                onClick={handleStartBatch}
                disabled={totalCount === 0}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '10px 24px',
                  fontSize: '14px',
                  fontWeight: 600,
                  color: '#ffffff',
                  background: totalCount === 0 ? '#94a3b8' : '#16a34a',
                  borderRadius: '8px',
                  boxShadow: '0 2px 4px rgba(22,163,74,0.2)',
                  cursor: totalCount === 0 ? 'not-allowed' : 'pointer',
                }}
              >
                <Play size={16} /> 开始处理 ({totalCount})
              </button>
            ) : (
              <button
                onClick={handleCancelBatch}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '10px 24px',
                  fontSize: '14px',
                  fontWeight: 600,
                  color: '#ffffff',
                  background: '#dc2626',
                  borderRadius: '8px',
                  boxShadow: '0 2px 4px rgba(220,38,38,0.2)',
                }}
              >
                <Square size={16} /> 停止取消
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Progress & Stats Bar */}
      <div
        style={{
          background: '#ffffff',
          borderRadius: '12px',
          padding: '16px 24px',
          marginBottom: '24px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '10px',
          }}
        >
          <div style={{ display: 'flex', gap: '20px', fontSize: '14px', fontWeight: 500 }}>
            <span style={{ color: '#475569' }}>待处理总数: <strong>{totalCount}</strong></span>
            <span style={{ color: '#16a34a' }}>成功: <strong>{successCount}</strong></span>
            <span style={{ color: '#dc2626' }}>失败: <strong>{failedCount}</strong></span>
          </div>
          <span style={{ fontSize: '14px', fontWeight: 600, color: '#0284c7' }}>
            {overallProgress}%
          </span>
        </div>

        {/* Progress Bar */}
        <div
          style={{
            width: '100%',
            height: '8px',
            background: '#e2e8f0',
            borderRadius: '4px',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${overallProgress}%`,
              height: '100%',
              background: '#0284c7',
              borderRadius: '4px',
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>

      {/* Task Item Cards List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {tasks.length === 0 ? (
          <div
            style={{
              background: '#ffffff',
              borderRadius: '12px',
              padding: '48px',
              textAlign: 'center',
              border: '1px solid #e2e8f0',
              color: '#64748b',
            }}
          >
            <ListMusic size={48} style={{ margin: '0 auto 12px', color: '#cbd5e1' }} />
            <p style={{ fontSize: '15px', fontWeight: 500 }}>未扫描到音频文件</p>
            <p style={{ fontSize: '13px', color: '#94a3b8', marginTop: '4px' }}>
              请输入路径或将 NCM 文件放入项目目录后点击“扫描路径”
            </p>
          </div>
        ) : (
          tasks.map((item) => (
            <div
              key={item.id}
              style={{
                background: '#ffffff',
                borderRadius: '12px',
                padding: '16px 20px',
                border: '1px solid #e2e8f0',
                boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '16px',
              }}
            >
              {/* Left Cover & File Info */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flex: 1, minWidth: 0 }}>
                {/* Cover Image or Fallback Icon */}
                <div
                  style={{
                    width: '52px',
                    height: '52px',
                    borderRadius: '8px',
                    overflow: 'hidden',
                    background: '#f1f5f9',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    border: '1px solid #e2e8f0',
                  }}
                >
                  {item.cover_url ? (
                    <img
                      src={item.cover_url}
                      alt={item.title || item.filename}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  ) : (
                    <FileAudio size={24} color="#64748b" />
                  )}
                </div>

                {/* Info Text */}
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <h3
                      style={{
                        fontSize: '15px',
                        fontWeight: 600,
                        color: '#0f172a',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {item.title || item.filename}
                    </h3>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: '#e0f2fe',
                        color: '#0369a1',
                      }}
                    >
                      {item.ext}
                    </span>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      fontSize: '13px',
                      color: '#64748b',
                      marginTop: '3px',
                    }}
                  >
                    <span>{item.artists.length > 0 ? item.artists.join(', ') : '未知歌手'}</span>
                    {item.album && <span>• {item.album}</span>}
                  </div>

                  {item.error_msg && (
                    <div style={{ fontSize: '12px', color: '#dc2626', marginTop: '4px' }}>
                      错误: {item.error_msg}
                    </div>
                  )}
                </div>
              </div>

              {/* Status Badge & Progress */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexShrink: 0 }}>
                {item.status === 'pending' && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '13px',
                      fontWeight: 500,
                      background: '#f1f5f9',
                      color: '#64748b',
                    }}
                  >
                    <Clock size={14} /> 等待中
                  </span>
                )}

                {item.status === 'processing' && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '13px',
                      fontWeight: 500,
                      background: '#e0f2fe',
                      color: '#0284c7',
                    }}
                  >
                    <Radio size={14} className="spin" /> 处理中...
                  </span>
                )}

                {item.status === 'success' && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '13px',
                      fontWeight: 500,
                      background: '#dcfce7',
                      color: '#15803d',
                    }}
                  >
                    <CheckCircle2 size={14} /> 处理成功
                  </span>
                )}

                {item.status === 'failed' && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '13px',
                      fontWeight: 500,
                      background: '#fee2e2',
                      color: '#b91c1c',
                    }}
                  >
                    <AlertCircle size={14} /> 失败
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Log Console Panel */}
      {logMessages.length > 0 && (
        <div
          style={{
            marginTop: '32px',
            background: '#ffffff',
            borderRadius: '12px',
            padding: '16px 20px',
            border: '1px solid #e2e8f0',
          }}
        >
          <h4 style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', marginBottom: '8px' }}>
            系统实时转换日志
          </h4>
          <div
            style={{
              maxHeight: '120px',
              overflowY: 'auto',
              fontSize: '12px',
              fontFamily: 'monospace',
              color: '#334155',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
            }}
          >
            {logMessages.map((log, idx) => (
              <div key={idx}>• {log}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
