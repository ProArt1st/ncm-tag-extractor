export type TaskStatus = 'pending' | 'processing' | 'success' | 'failed';

export interface TaskItem {
  id: string;
  filename: string;
  source_path: string;
  output_path?: string | null;
  ext: string;
  status: TaskStatus;
  progress: number;
  title?: string | null;
  artists: string[];
  album?: string | null;
  cover_url?: string | null;
  has_lyrics: boolean;
  netease_id?: number | string | null;
  warnings: string[];
  error_msg?: string | null;
}

export interface ProgressMessage {
  event:
    | 'scan_result'
    | 'item_update'
    | 'batch_start'
    | 'batch_complete'
    | 'log';
  total: number;
  completed: number;
  item?: TaskItem | null;
  message?: string | null;
}

export interface AppConfig {
  input_dirs: string[];
  output_dir: string;
  recursive: boolean;
  enrich_netease: boolean;
  sort_by: 'name' | 'mtime' | 'mtime_desc';
  enable_mtime_filter: boolean;
  process_after_mtime: string;
  auto_update_mtime: boolean;
  only_process_failed: boolean;
}
