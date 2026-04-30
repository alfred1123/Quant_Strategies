import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RangeFields from './RangeFields';

describe('RangeFields', () => {
  const defaultValue = { min: 5, max: 100, step: 5 };

  it('renders three fields with correct labels', () => {
    render(<RangeFields label="Win" value={defaultValue} onChange={vi.fn()} />);
    expect(screen.getByLabelText('Win Min')).toBeInTheDocument();
    expect(screen.getByLabelText('Win Max')).toBeInTheDocument();
    expect(screen.getByLabelText('Win Step')).toBeInTheDocument();
  });

  it('calls onChange with correct patch when min changes', () => {
    const onChange = vi.fn();
    render(<RangeFields label="Win" value={defaultValue} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Win Min'), { target: { value: '10' } });
    expect(onChange).toHaveBeenCalledWith({ min: 10 });
  });

  it('calls onChange with correct patch when max changes', () => {
    const onChange = vi.fn();
    render(<RangeFields label="Sig" value={defaultValue} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Sig Max'), { target: { value: '200' } });
    expect(onChange).toHaveBeenCalledWith({ max: 200 });
  });

  it('calls onChange with correct patch when step changes', () => {
    const onChange = vi.fn();
    render(<RangeFields label="Win" value={defaultValue} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Win Step'), { target: { value: '10' } });
    expect(onChange).toHaveBeenCalledWith({ step: 10 });
  });

  it('disables Min and Max when disabledMinMax is true', () => {
    render(<RangeFields label="Win" value={defaultValue} onChange={vi.fn()} disabledMinMax />);
    expect(screen.getByLabelText('Win Min')).toBeDisabled();
    expect(screen.getByLabelText('Win Max')).toBeDisabled();
    expect(screen.getByLabelText('Win Step')).not.toBeDisabled();
  });
});
