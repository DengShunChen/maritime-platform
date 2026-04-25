import React from 'react';
import './KeyboardShortcutsHelp.css';

interface KeyboardShortcutsHelpProps {
  onClose: () => void;
}

const SHORTCUTS = [
  { keys: ['Space'], description: '播放 / 暫停' },
  { keys: ['←'], description: '上一個時間點' },
  { keys: ['→'], description: '下一個時間點' },
  { keys: ['↑'], description: '加快播放速度' },
  { keys: ['↓'], description: '減慢播放速度' },
  { keys: ['Home'], description: '跳到第一個時間點' },
  { keys: ['End'], description: '跳到最後一個時間點' },
  { keys: ['F'], description: '切換全螢幕' },
  { keys: ['?'], description: '顯示快捷鍵說明' },
  { keys: ['Esc'], description: '關閉此視窗' },
];

export const KeyboardShortcutsHelp: React.FC<KeyboardShortcutsHelpProps> = ({ onClose }) => {
  return (
    <div className="shortcuts-overlay" onClick={onClose}>
      <div className="shortcuts-modal" onClick={e => e.stopPropagation()}>
        <div className="shortcuts-header">
          <h2>⌨️ 鍵盤快捷鍵</h2>
          <button className="shortcuts-close" onClick={onClose} aria-label="關閉">
            ✕
          </button>
        </div>
        <div className="shortcuts-list">
          {SHORTCUTS.map((shortcut, index) => (
            <div key={index} className="shortcut-item">
              <div className="shortcut-keys">
                {shortcut.keys.map((key, keyIndex) => (
                  <kbd key={keyIndex}>{key}</kbd>
                ))}
              </div>
              <span className="shortcut-desc">{shortcut.description}</span>
            </div>
          ))}
        </div>
        <div className="shortcuts-footer">
          按 <kbd>?</kbd> 或 <kbd>Esc</kbd> 關閉此視窗
        </div>
      </div>
    </div>
  );
};
