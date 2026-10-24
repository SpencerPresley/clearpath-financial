import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { CheckboxField, CheckboxGroupField, SelectField, TextInput } from './fields';

describe('form fields', () => {
  it('shows an error message and marks the input invalid', () => {
    render(<TextInput label="Title" value="" onChange={vi.fn()} errorMessage="Enter a title." />);
    expect(screen.getByLabelText('Title')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Enter a title.')).toBeInTheDocument();
  });

  it('selects an option', async () => {
    const onChange = vi.fn();
    render(
      <SelectField
        label="Product"
        value={null}
        onChange={onChange}
        options={[
          { id: 'personal_loan', label: 'Personal loan' },
          { id: 'credit_card', label: 'Credit card' },
        ]}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /Product/ }));
    await userEvent.click(await screen.findByRole('option', { name: 'Credit card' }));
    expect(onChange).toHaveBeenCalledWith('credit_card');
  });

  it('toggles checkboxes in a group and standalone', async () => {
    function Harness() {
      const [markets, setMarkets] = useState<('national' | 'CA')[]>(['national']);
      const [prescreen, setPrescreen] = useState(false);
      return (
        <>
          <CheckboxGroupField
            label="Markets"
            value={markets}
            onChange={setMarkets}
            options={[
              { id: 'national', label: 'National' },
              { id: 'CA', label: 'California' },
            ]}
          />
          <CheckboxField isSelected={prescreen} onChange={setPrescreen}>
            Prescreened firm offer
          </CheckboxField>
          <output>{`${markets.join(',')}|${String(prescreen)}`}</output>
        </>
      );
    }
    render(<Harness />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'California' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'Prescreened firm offer' }));
    expect(screen.getByRole('status')).toHaveTextContent('national,CA|true');
  });
});
