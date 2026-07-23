import { useState, useEffect, useRef } from 'react';
import {
  Music,
  FolderSearch,
  Play,
  Square,
  Sparkles,
  ListMusic,
  RefreshCw,
  Calendar,
  AlertTriangle,
  FolderOutput,
  FolderPlus,
  X,
  Filter,
  Eye,
  Search,
} from 'lucide-react';
import type { TaskItem, ProgressMessage, AppConfig } from './types';

interface FailedItemRecord {
  path: string;
  name: string;
  reason: string;
  time: string;
}

export function App() {
  const [inputDirs, setInputDirs] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useState<string>('');
  const [recursive, setRecursive] = useState<boolean>(false);
  const [enrichNetease, setEnrichNetease] = useState<boolean>(true);
  const [sortBy, setSortBy] = useState<'name' | 'mtime' | 'mtime_desc'>('name');
  const [enableMtimeFilter, setEnableMtimeFilter] = useState<boolean>(false);
  const [processAfterMtime, setProcessAfterMtime] = useState<string>('');
  const [autoUpdateMtime, setAutoUpdateMtime] = useState<boolean>(true);
  const [onlyProcessFailed, setOnlyProcessFailed] = useState<boolean>(false);

  const [totalCount, setTotalCount] = useState<number>(0);
  const [processedCount, setProcessedCount] = useState<number>(0);
  const [successCount, setSuccessCount] = useState<number>(0);
  const [failedCount, setFailedCount] = useState<number>(0);

  const [scannedItems, setScannedItems] = useState<TaskItem[]>([]);
  const [failedListRecords, setFailedListRecords] = useState<FailedItemRecord[]>([]);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [logMessages, setLogMessages] = useState<string[]>([]);

  // Modals States
  const [showPreviewModal, setShowPreviewModal] = useState<boolean>(false);
  const [showFailedModal, setShowFailedModal] = useState<boolean>(false);
  const [previewSearch, setPreviewSearch] = useState<string>('');
  const [previewFormatFilter, setPreviewFormatFilter] = useState<'all' | 'ncm' | 'flac' | 'mp3'>('all');

  const wsRef = useRef<WebSocket | null>(null);
  const isFirstLoadRef = useRef<boolean>(true);

  // Overall Progress (Locked at 100% when completed)
  const overallProgress =
    totalCount > 0
      ? Math.min(100, Math.round((processedCount / totalCount) * 100))
      : 0;

  // Format count stats for preview filter
  const ncmCount = scannedItems.filter((i) => i.ext === 'ncm').length;
  const flacCount = scannedItems.filter((i) => i.ext === 'flac').length;
  const mp3Count = scannedItems.filter((i) => i.ext === 'mp3').length;

  // Filtered preview items list
  const filteredPreviewItems = scannedItems.filter((item) => {
    const matchesSearch =
      !previewSearch ||
      item.filename.toLowerCase().includes(previewSearch.toLowerCase()) ||
      item.source_path.toLowerCase().includes(previewSearch.toLowerCase());
    const matchesFormat =
      previewFormatFilter === 'all' || item.ext === previewFormatFilter;
    return matchesSearch && matchesFormat;
  });

  const getApiBase = () => {
    return window.location.port === '5173' ? 'http://127.0.0.1:8000' : '';
  };

  const fetchFailedList = () => {
    fetch(`${getApiBase()}/api/failed-list`)
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) setFailedListRecords(data);
      })
      .catch(() => {});
  };

  // Initialize WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.port === '5173' ? '127.0.0.1:8000' : (window.location.host || '127.0.0.1:8000');
    const wsUrl = `${protocol}//${host}/api/ws/progress`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket Connected:', wsUrl);
    };

    ws.onmessage = (event) => {
      try {
        const msg: ProgressMessage = JSON.parse(event.data);
        if (msg.event === 'batch_start') {
          setIsProcessing(true);
          setProcessedCount(0);
          setSuccessCount(0);
          setFailedCount(0);
        } else if (msg.event === 'batch_complete') {
          setIsProcessing(false);
          fetchFailedList();
          // Refetch config to update processAfterMtime automatically WITHOUT resetting progress!
          fetch(`${getApiBase()}/api/config`)
            .then((res) => res.json())
            .then((cfg: Partial<AppConfig>) => {
              if (cfg.process_after_mtime !== undefined) {
                setProcessAfterMtime(String(cfg.process_after_mtime));
              }
            })
            .catch(() => {});
        } else if (msg.event === 'item_update' && msg.item) {
          const item = msg.item;
          if (item.status === 'success') {
            setSuccessCount((prev) => prev + 1);
            setProcessedCount((prev) => prev + 1);
          } else if (item.status === 'failed') {
            setFailedCount((prev) => prev + 1);
            setProcessedCount((prev) => prev + 1);
          }
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

  // Initial auto scan & config load on mount
  useEffect(() => {
    fetchFailedList();
    fetch(`${getApiBase()}/api/config`)
      .then((res) => res.json())
      .then((cfg: Partial<AppConfig>) => {
        const initialInputDirs = Array.isArray(cfg.input_dirs) ? cfg.input_dirs : [];
        const initialRecursive = typeof cfg.recursive === 'boolean' ? cfg.recursive : false;
        const initialSortBy = cfg.sort_by || 'name';
        const initialEnableMtimeFilter = typeof cfg.enable_mtime_filter === 'boolean' ? cfg.enable_mtime_filter : false;
        const initialProcessAfterMtime = cfg.process_after_mtime !== undefined ? String(cfg.process_after_mtime) : '';
        const initialOnlyProcessFailed = typeof cfg.only_process_failed === 'boolean' ? cfg.only_process_failed : false;

        setInputDirs(initialInputDirs);
        if (cfg.output_dir !== undefined) setOutputDir(cfg.output_dir);
        setRecursive(initialRecursive);
        if (typeof cfg.enrich_netease === 'boolean') setEnrichNetease(cfg.enrich_netease);
        setSortBy(initialSortBy);
        setEnableMtimeFilter(initialEnableMtimeFilter);
        setProcessAfterMtime(initialProcessAfterMtime);
        if (typeof cfg.auto_update_mtime === 'boolean') setAutoUpdateMtime(cfg.auto_update_mtime);
        setOnlyProcessFailed(initialOnlyProcessFailed);

        // Perform initial scan with loaded config parameters
        fetch(`${getApiBase()}/api/scan`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            paths: initialInputDirs,
            recursive: initialRecursive,
            sort_by: initialSortBy,
            enable_mtime_filter: initialEnableMtimeFilter,
            process_after_mtime: initialProcessAfterMtime,
            only_process_failed: initialOnlyProcessFailed,
          }),
        })
          .then((res) => res.json())
          .then((data) => {
            setTotalCount(data.total || 0);
            setScannedItems(data.items || []);
          })
          .catch(() => {});

        setTimeout(() => {
          isFirstLoadRef.current = false;
        }, 100);
      })
      .catch(() => {
        isFirstLoadRef.current = false;
      });
  }, []);

  // Auto save config on change without triggering handleScan()
  useEffect(() => {
    if (isFirstLoadRef.current) return;

    const timer = setTimeout(() => {
      fetch(`${getApiBase()}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_dirs: inputDirs,
          output_dir: outputDir,
          recursive: recursive,
          enrich_netease: enrichNetease,
          sort_by: sortBy,
          enable_mtime_filter: enableMtimeFilter,
          process_after_mtime: processAfterMtime,
          auto_update_mtime: autoUpdateMtime,
          only_process_failed: onlyProcessFailed,
        }),
      }).catch((err) => console.error('Auto save config error:', err));
    }, 300);

    return () => clearTimeout(timer);
  }, [
    inputDirs,
    outputDir,
    recursive,
    enrichNetease,
    sortBy,
    enableMtimeFilter,
    processAfterMtime,
    autoUpdateMtime,
    onlyProcessFailed,
  ]);

  const handleRemoveInputDir = (indexToRemove: number) => {
    const nextDirs = inputDirs.filter((_, idx) => idx !== indexToRemove);
    setInputDirs(nextDirs);
    handleScanWithDirs(nextDirs);
  };

  const handleSelectInputDir = async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/select-dir`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'success' && data.path) {
          if (!inputDirs.includes(data.path)) {
            const nextDirs = [...inputDirs, data.path];
            setInputDirs(nextDirs);
            handleScanWithDirs(nextDirs);
          }
        }
      }
    } catch (err) {
      console.error('Select dir error:', err);
    }
  };

  const handleSelectOutputDir = async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/select-dir`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'success' && data.path) {
          setOutputDir(data.path);
        }
      }
    } catch (err) {
      console.error('Select output dir error:', err);
    }
  };

  const handleClearOutputDir = () => {
    setOutputDir('');
  };

  const handleScanWithDirs = (dirs: string[]) => {
    fetch(`${getApiBase()}/api/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paths: dirs,
        recursive: recursive,
        sort_by: sortBy,
        enable_mtime_filter: enableMtimeFilter,
        process_after_mtime: processAfterMtime,
        only_process_failed: onlyProcessFailed,
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        setTotalCount(data.total || 0);
        setScannedItems(data.items || []);
        setProcessedCount(0);
        setSuccessCount(0);
        setFailedCount(0);
      })
      .catch(() => {});
  };

  const handleScan = async () => {
    handleScanWithDirs(inputDirs);
  };

  const handleStartBatch = async () => {
    if (isProcessing) return;
    try {
      setProcessedCount(0);
      setSuccessCount(0);
      setFailedCount(0);

      const res = await fetch(`${getApiBase()}/api/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paths: inputDirs,
          output_dir: outputDir,
          enrich_netease: enrichNetease,
          recursive: recursive,
          sort_by: sortBy,
          enable_mtime_filter: enableMtimeFilter,
          process_after_mtime: processAfterMtime,
          auto_update_mtime: autoUpdateMtime,
          only_process_failed: onlyProcessFailed,
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
              padding: '9px 18px',
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

      {/* Main Control Panel */}
      <div
        style={{
          background: '#ffffff',
          borderRadius: '12px',
          padding: '24px',
          marginBottom: '24px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        {/* Section 1: Input Paths Cards Container */}
        <div style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <label style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <FolderSearch size={16} color="#0284c7" />
              输入文件夹列表 ({inputDirs.length} 个)
            </label>

            <button
              type="button"
              onClick={handleSelectInputDir}
              style={{
                padding: '5px 12px',
                fontSize: '12px',
                fontWeight: 500,
                color: '#0284c7',
                background: '#f0f9ff',
                border: '1px solid #bae6fd',
                borderRadius: '6px',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <FolderPlus size={14} /> 添加输入文件夹
            </button>
          </div>

          {/* Cards List Grid */}
          {inputDirs.length === 0 ? (
            <div
              style={{
                padding: '14px 16px',
                background: '#f8fafc',
                border: '1px dashed #cbd5e1',
                borderRadius: '8px',
                fontSize: '13px',
                color: '#94a3b8',
                textAlign: 'center',
              }}
            >
              未添加特定输入文件夹 (留空将自动扫描项目默认目录)
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {inputDirs.map((pathStr, index) => (
                <div
                  key={index}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 14px',
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '13px',
                    color: '#334155',
                    fontFamily: 'monospace',
                  }}
                >
                  <span style={{ wordBreak: 'break-all', paddingRight: '12px' }}>{pathStr}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveInputDir(index)}
                    title="移除此路径"
                    style={{
                      border: 'none',
                      background: 'transparent',
                      color: '#ef4444',
                      cursor: 'pointer',
                      padding: '2px',
                      display: 'flex',
                      alignItems: 'center',
                      borderRadius: '4px',
                    }}
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Section 2: Output Dir Cards Container */}
        <div style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <label style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <FolderOutput size={16} color="#0284c7" />
              输出保存文件夹
            </label>

            {!outputDir && (
              <button
                type="button"
                onClick={handleSelectOutputDir}
                style={{
                  padding: '5px 12px',
                  fontSize: '12px',
                  fontWeight: 500,
                  color: '#0284c7',
                  background: '#f0f9ff',
                  border: '1px solid #bae6fd',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <FolderPlus size={14} /> 添加输出文件夹
              </button>
            )}
          </div>

          {!outputDir ? (
            <div
              style={{
                padding: '14px 16px',
                background: '#f8fafc',
                border: '1px dashed #cbd5e1',
                borderRadius: '8px',
                fontSize: '13px',
                color: '#94a3b8',
                textAlign: 'center',
              }}
            >
              未指定输出文件夹 (默认保存在原音乐所在目录)
            </div>
          ) : (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 14px',
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                fontSize: '13px',
                color: '#334155',
                fontFamily: 'monospace',
              }}
            >
              <span style={{ wordBreak: 'break-all', paddingRight: '12px' }}>{outputDir}</span>
              <button
                type="button"
                onClick={handleClearOutputDir}
                title="清除自定义输出文件夹，恢复保存在原目录"
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: '#ef4444',
                  cursor: 'pointer',
                  padding: '2px',
                  display: 'flex',
                  alignItems: 'center',
                  borderRadius: '4px',
                }}
              >
                <X size={16} />
              </button>
            </div>
          )}
        </div>

        {/* Section 3: Expanded Options Grid */}
        <div
          style={{
            paddingTop: '16px',
            borderTop: '1px solid #f1f5f9',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1.2fr',
            gap: '16px',
            marginBottom: '20px',
          }}
        >
          {/* Sort Method Selector */}
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
              <ListMusic size={14} style={{ verticalAlign: '-2px', marginRight: '4px' }} />
              转换处理排序方式:
            </label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              style={{
                width: '100%',
                padding: '8px 10px',
                fontSize: '13px',
                border: '1px solid #cbd5e1',
                borderRadius: '6px',
                background: '#ffffff',
                color: '#334155',
              }}
            >
              <option value="name">按文件名升序</option>
              <option value="mtime">按修改时间升序 (从旧到新)</option>
              <option value="mtime_desc">按修改时间降序 (从新到旧)</option>
            </select>
          </div>

          {/* mtime Timestamp Filter */}
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
              <Calendar size={14} style={{ verticalAlign: '-2px', marginRight: '4px' }} />
              记录保存转换时间节点:
            </label>
            <input
              type="text"
              placeholder="YYYY-MM-DD HH:mm:ss"
              value={processAfterMtime}
              onChange={(e) => setProcessAfterMtime(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                fontSize: '13px',
                border: '1px solid #cbd5e1',
                borderRadius: '6px',
                background: '#ffffff',
                color: '#334155',
              }}
            />
          </div>

          {/* Checkboxes Group */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', justifyContent: 'center' }}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#0369a1', fontWeight: 500, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={enableMtimeFilter}
                onChange={(e) => setEnableMtimeFilter(e.target.checked)}
                style={{ accentColor: '#0284c7' }}
              />
              <Filter size={13} color="#0284c7" />
              启用时间节点过滤 (只转换该时间之后的音频)
            </label>

            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#475569', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={autoUpdateMtime}
                onChange={(e) => setAutoUpdateMtime(e.target.checked)}
                style={{ accentColor: '#0284c7' }}
              />
              转换成功后自动保存时间节点
            </label>

            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#dc2626', fontWeight: 500, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={onlyProcessFailed}
                onChange={(e) => setOnlyProcessFailed(e.target.checked)}
                style={{ accentColor: '#dc2626' }}
              />
              <AlertTriangle size={13} color="#dc2626" />
              仅选择上次处理失败的文件 (fail.json)
            </label>
          </div>
        </div>

        {/* Section 4: Mode & Action Row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingTop: '16px',
            borderTop: '1px solid #f1f5f9',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', gap: '20px', alignItems: 'center', flexWrap: 'wrap' }}>
            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '13px',
                color: '#0f172a',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              <Sparkles size={16} color="#0284c7" />
              数据来源: <strong>网易云高保真元数据 & 原画封面</strong>
            </label>

            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
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
              纯离线解密 NCM
            </label>

            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
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
                <Play size={16} /> 开始处理 ({totalCount} 个音频)
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

      {/* Progress & Stats Bar (Locked at 100% when complete) */}
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
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center', fontSize: '14px', fontWeight: 500, flexWrap: 'wrap' }}>
            <span style={{ color: '#475569' }}>准备处理总数: <strong>{totalCount}</strong></span>

            {totalCount > 0 && (
              <button
                type="button"
                onClick={() => setShowPreviewModal(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '3px 10px',
                  fontSize: '12px',
                  fontWeight: 500,
                  color: '#0284c7',
                  background: '#f0f9ff',
                  border: '1px solid #bae6fd',
                  borderRadius: '6px',
                  cursor: 'pointer',
                }}
              >
                <Eye size={13} /> 预览要处理的文件清单
              </button>
            )}

            {(failedCount > 0 || failedListRecords.length > 0) && (
              <button
                type="button"
                onClick={() => {
                  fetchFailedList();
                  setShowFailedModal(true);
                }}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '3px 10px',
                  fontSize: '12px',
                  fontWeight: 500,
                  color: '#0284c7',
                  background: '#f0f9ff',
                  border: '1px solid #bae6fd',
                  borderRadius: '6px',
                  cursor: 'pointer',
                }}
              >
                <AlertTriangle size={13} color="#0284c7" /> 预览失败清单 ({failedListRecords.length || failedCount})
              </button>
            )}

            <span style={{ color: '#0284c7' }}>已处理: <strong>{processedCount}</strong></span>
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

      {/* Log Console Panel - Always Visible */}
      <div
        style={{
          marginTop: '16px',
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
          {logMessages.length === 0 ? (
            <div style={{ color: '#94a3b8' }}>• [系统] 暂无转换日志，系统就绪中...</div>
          ) : (
            logMessages.map((log, idx) => <div key={idx}>• {log}</div>)
          )}
        </div>
      </div>

      {/* Modal Dialog: Pre-flight Audio File List Preview */}
      {showPreviewModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(15, 23, 42, 0.5)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#ffffff',
              borderRadius: '16px',
              width: '100%',
              maxWidth: '720px',
              maxHeight: '85vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: '18px 24px',
                borderBottom: '1px solid #e2e8f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Eye size={18} color="#0284c7" />
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#0f172a' }}>
                  准备处理音频文件预检清单 ({scannedItems.length})
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowPreviewModal(false)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '4px',
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Controls: Search & Format Filter Pills */}
            <div style={{ padding: '16px 24px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', gap: '12px', marginBottom: '12px', alignItems: 'center' }}>
                <div style={{ position: 'relative', flex: 1 }}>
                  <Search
                    size={16}
                    color="#94a3b8"
                    style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }}
                  />
                  <input
                    type="text"
                    placeholder="搜索文件名..."
                    value={previewSearch}
                    onChange={(e) => setPreviewSearch(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '7px 10px 7px 32px',
                      fontSize: '13px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      background: '#ffffff',
                      color: '#1e293b',
                    }}
                  />
                </div>
              </div>

              {/* Filter Pills */}
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => setPreviewFormatFilter('all')}
                  style={{
                    padding: '4px 12px',
                    fontSize: '12px',
                    fontWeight: 500,
                    borderRadius: '20px',
                    border: '1px solid',
                    borderColor: previewFormatFilter === 'all' ? '#0284c7' : '#cbd5e1',
                    background: previewFormatFilter === 'all' ? '#e0f2fe' : '#ffffff',
                    color: previewFormatFilter === 'all' ? '#0369a1' : '#475569',
                    cursor: 'pointer',
                  }}
                >
                  全部 ({scannedItems.length})
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewFormatFilter('ncm')}
                  style={{
                    padding: '4px 12px',
                    fontSize: '12px',
                    fontWeight: 500,
                    borderRadius: '20px',
                    border: '1px solid',
                    borderColor: previewFormatFilter === 'ncm' ? '#0284c7' : '#cbd5e1',
                    background: previewFormatFilter === 'ncm' ? '#e0f2fe' : '#ffffff',
                    color: previewFormatFilter === 'ncm' ? '#0369a1' : '#475569',
                    cursor: 'pointer',
                  }}
                >
                  🔒 NCM ({ncmCount})
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewFormatFilter('flac')}
                  style={{
                    padding: '4px 12px',
                    fontSize: '12px',
                    fontWeight: 500,
                    borderRadius: '20px',
                    border: '1px solid',
                    borderColor: previewFormatFilter === 'flac' ? '#0284c7' : '#cbd5e1',
                    background: previewFormatFilter === 'flac' ? '#e0f2fe' : '#ffffff',
                    color: previewFormatFilter === 'flac' ? '#0369a1' : '#475569',
                    cursor: 'pointer',
                  }}
                >
                  🎼 FLAC ({flacCount})
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewFormatFilter('mp3')}
                  style={{
                    padding: '4px 12px',
                    fontSize: '12px',
                    fontWeight: 500,
                    borderRadius: '20px',
                    border: '1px solid',
                    borderColor: previewFormatFilter === 'mp3' ? '#0284c7' : '#cbd5e1',
                    background: previewFormatFilter === 'mp3' ? '#e0f2fe' : '#ffffff',
                    color: previewFormatFilter === 'mp3' ? '#0369a1' : '#475569',
                    cursor: 'pointer',
                  }}
                >
                  🎧 MP3 ({mp3Count})
                </button>
              </div>
            </div>

            {/* Modal Body: File List */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 24px', maxHeight: '380px' }}>
              {filteredPreviewItems.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '32px', color: '#94a3b8', fontSize: '13px' }}>
                  未筛选到匹配的音频文件
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {filteredPreviewItems.map((item, idx) => (
                    <div
                      key={item.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 12px',
                        background: idx % 2 === 0 ? '#ffffff' : '#f8fafc',
                        borderRadius: '6px',
                        border: '1px solid #f1f5f9',
                        fontSize: '13px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, flex: 1 }}>
                        <span style={{ fontSize: '12px', color: '#94a3b8', width: '24px', textAlign: 'right' }}>
                          {idx + 1}.
                        </span>
                        <span
                          title={item.source_path}
                          style={{
                            fontWeight: 500,
                            color: '#1e293b',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {item.filename}
                        </span>
                      </div>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          textTransform: 'uppercase',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: '#e0f2fe',
                          color: '#0369a1',
                          marginLeft: '12px',
                          flexShrink: 0,
                        }}
                      >
                        {item.ext}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: '14px 24px',
                borderTop: '1px solid #e2e8f0',
                background: '#f8fafc',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span style={{ fontSize: '13px', color: '#64748b' }}>
                显示 {filteredPreviewItems.length} / {scannedItems.length} 个音频文件
              </span>
              <button
                type="button"
                onClick={() => setShowPreviewModal(false)}
                style={{
                  padding: '7px 18px',
                  fontSize: '13px',
                  fontWeight: 500,
                  color: '#334155',
                  background: '#ffffff',
                  border: '1px solid #cbd5e1',
                  borderRadius: '6px',
                  cursor: 'pointer',
                }}
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Dialog: Failed Items Details Preview (fail.json) */}
      {showFailedModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(15, 23, 42, 0.5)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#ffffff',
              borderRadius: '16px',
              width: '100%',
              maxWidth: '720px',
              maxHeight: '85vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: '18px 24px',
                borderBottom: '1px solid #e2e8f0',
                background: '#ffffff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <AlertTriangle size={18} color="#0284c7" />
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#0f172a' }}>
                  转换失败音频明细清单 (fail.json)
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowFailedModal(false)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '4px',
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Body: Failed List Items */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px', maxHeight: '420px' }}>
              {failedListRecords.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '32px', color: '#16a34a', fontSize: '14px', fontWeight: 500 }}>
                  🎉 太棒了，当前没有任何失败文件记录！
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {failedListRecords.map((item, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '12px 14px',
                        background: '#fef2f2',
                        borderRadius: '8px',
                        border: '1px solid #fecaca',
                        fontSize: '13px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600, color: '#991b1b' }}>{item.name}</span>
                        <span style={{ fontSize: '11px', color: '#991b1b', opacity: 0.8 }}>{item.time}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: '#dc2626', marginTop: '2px', wordBreak: 'break-all' }}>
                        <strong>失败原因:</strong> {item.reason}
                      </div>
                      <div style={{ fontSize: '11px', color: '#7f1d1d', marginTop: '4px', fontFamily: 'monospace', opacity: 0.7, wordBreak: 'break-all' }}>
                        {item.path}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: '14px 24px',
                borderTop: '1px solid #e2e8f0',
                background: '#f8fafc',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span style={{ fontSize: '13px', color: '#64748b' }}>
                共 {failedListRecords.length} 个失败条目
              </span>
              <button
                type="button"
                onClick={() => setShowFailedModal(false)}
                style={{
                  padding: '7px 18px',
                  fontSize: '13px',
                  fontWeight: 500,
                  color: '#334155',
                  background: '#ffffff',
                  border: '1px solid #cbd5e1',
                  borderRadius: '6px',
                  cursor: 'pointer',
                }}
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
