import React from 'react';

interface Variable {
  id: string;
  name: string;
  description: string;
  units: string;
}

interface VariableSelectorProps {
  variables: Variable[];
  selectedVariable: string;
  onVariableChange: (variableId: string) => void;
}

export const VariableSelector: React.FC<VariableSelectorProps> = ({
  variables,
  selectedVariable,
  onVariableChange
}) => {
  const selected = variables.find(v => v.id === selectedVariable);

  return (
    <div style={{
      position: 'absolute',
      top: '20px',
      left: '20px',
      zIndex: 1000,
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderRadius: '8px',
      padding: '12px 16px',
      boxShadow: '0 2px 10px rgba(0,0,0,0.15)',
      minWidth: '280px',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      <label style={{
        display: 'block',
        fontSize: '13px',
        fontWeight: '600',
        color: '#333',
        marginBottom: '8px',
        textTransform: 'uppercase',
        letterSpacing: '0.5px'
      }}>
        氣象變數
      </label>

      <select
        value={selectedVariable}
        onChange={(e) => onVariableChange(e.target.value)}
        style={{
          width: '100%',
          padding: '8px 12px',
          fontSize: '14px',
          border: '1.5px solid #ddd',
          borderRadius: '6px',
          backgroundColor: 'white',
          cursor: 'pointer',
          outline: 'none',
          transition: 'border-color 0.2s',
        }}
        onFocus={(e) => e.target.style.borderColor = '#4A90E2'}
        onBlur={(e) => e.target.style.borderColor = '#ddd'}
      >
        {variables.map(variable => (
          <option key={variable.id} value={variable.id}>
            {variable.name} ({variable.units})
          </option>
        ))}
      </select>

      {selected && (
        <div style={{
          marginTop: '10px',
          paddingTop: '10px',
          borderTop: '1px solid #eee',
          fontSize: '12px',
          color: '#666',
          lineHeight: '1.5'
        }}>
          <div style={{ fontWeight: '500', color: '#444', marginBottom: '4px' }}>
            {selected.description}
          </div>
          <div style={{ color: '#888' }}>
            單位: {selected.units}
          </div>
        </div>
      )}
    </div>
  );
};
