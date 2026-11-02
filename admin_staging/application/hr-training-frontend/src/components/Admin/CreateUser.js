import React, { useEffect, useMemo, useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  MenuItem,
  Alert,
  Grid,
} from '@mui/material';
import { userService } from '../../services/auth';

const initialFormState = {
  email: '',
  hr_id: '',
  name: '',
  title: '',
  branch_code: '',
  department: 'Retail',
};

const fieldConfig = [
  { name: 'email', label: 'Email', type: 'email', required: true, fullWidth: true },
  { name: 'hr_id', label: 'HR ID', required: true },
  { name: 'name', label: 'Full Name', required: true },
  { name: 'title', label: 'Title', required: true },
];

const titleOptions = [
  { value: 'Team Leader', label: 'Team Leader' },
  { value: 'indoor Sales Representative', label: 'indoor Sales Representative' },
  { value: 'Acting as Team Leader', label: 'Acting as Team Leader' },
];

const roleOptions = [
  { value: 'admin', label: 'Admin' },
  { value: 'hr', label: 'HR' },
  { value: 'Retail', label: 'Retail (Employee)' },
];

const CreateUser = ({ open, onClose, onUserCreated }) => {
  const [formData, setFormData] = useState({ ...initialFormState });
  const [branches, setBranches] = useState([]);
  const [loadingBranches, setLoadingBranches] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchBranches = async () => {
      setLoadingBranches(true);
      try {
        const response = await userService.getAudienceHierarchy();
        const regions = response.data?.data?.regions || [];
        const flattened = [];
        regions.forEach((region) => {
          region.areas?.forEach((area) => {
            area.branches?.forEach((branch) => {
              flattened.push({
                branch_code: branch.branch_code,
                branch_name: branch.branch_name,
                region: region.region,
                area: area.area,
                division: branch.division,
                sub_department: branch.sub_department,
              });
            });
          });
        });
        setBranches(flattened);
      } catch (err) {
        console.error('Failed to load branches', err);
        setError('Unable to load branch list. Please upload branches first.');
      } finally {
        setLoadingBranches(false);
      }
    };
    fetchBranches();
  }, []);

  const selectedBranch = useMemo(
    () => branches.find((branch) => branch.branch_code === formData.branch_code),
    [branches, formData.branch_code]
  );

  const handleChange = (name, value) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError('');

    try {
      await userService.createUser(formData);
      if (onUserCreated) {
        onUserCreated();
      }
      handleClose();
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to create user');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setFormData({ ...initialFormState });
    setError('');
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>Create New User</DialogTitle>
      <DialogContent>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Grid container spacing={2} sx={{ mt: 0.5 }}>
          {fieldConfig.map((field) => {
            if (field.name === 'title') {
              return (
                <Grid
                  item
                  xs={12}
                  sm={field.fullWidth ? 12 : 6}
                  key={field.name}
                  sx={{ minWidth: { xs: '100%', sm: 240 }, flex: '1 1 240px' }}
                >
                  <TextField
                    select
                    fullWidth
                    label={field.label}
                    value={formData[field.name]}
                    onChange={(e) => handleChange(field.name, e.target.value)}
                    margin="normal"
                    required={field.required}
                    SelectProps={{
                      displayEmpty: true,
                      renderValue: (selected) => selected || 'Select title',
                    }}
                    InputLabelProps={{ shrink: true }}
                  >
                    <MenuItem value="">Select title</MenuItem>
                    {titleOptions.map((option) => (
                      <MenuItem key={option.value} value={option.value}>
                        {option.label}
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
              );
            }

            return (
              <Grid item xs={12} sm={field.fullWidth ? 12 : 6} key={field.name}>
                <TextField
                  fullWidth
                  label={field.label}
                  type={field.type || 'text'}
                  value={formData[field.name]}
                  onChange={(e) => handleChange(field.name, e.target.value)}
                  margin="normal"
                  required={field.required}
                />
              </Grid>
            );
          })}

          <Grid item xs={12}>
            <TextField
              select
              fullWidth
              label="Branch"
              value={formData.branch_code}
              onChange={(e) => handleChange('branch_code', e.target.value)}
              margin="normal"
              required
              disabled={loadingBranches || branches.length === 0}
              helperText={
                loadingBranches
                  ? 'Loading branches...'
                  : branches.length
                  ? 'Select a branch to auto-use its region, area, division, and sub department.'
                  : 'No branches available. Please upload branches first.'
              }
            >
              {branches.map((branch) => (
                <MenuItem key={branch.branch_code} value={branch.branch_code}>
                  {branch.branch_name} ({branch.branch_code}) — {branch.area}, {branch.region}
                </MenuItem>
              ))}
            </TextField>
          </Grid>

          {selectedBranch ? (
            <Grid item xs={12}>
              <Alert severity="info" sx={{ mb: 0, mt: 1 }}>
                Region: <strong>{selectedBranch.region}</strong> · Area:{' '}
                <strong>{selectedBranch.area}</strong> · Division:{' '}
                <strong>{selectedBranch.division}</strong> · Sub Department:{' '}
                <strong>{selectedBranch.sub_department}</strong>
              </Alert>
            </Grid>
          ) : null}

          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              select
              label="Department / Role"
              value={formData.department}
              onChange={(e) => handleChange('department', e.target.value)}
              margin="normal"
              required
            >
              {roleOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>
          </Grid>

        </Grid>
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} variant="contained" disabled={loading}>
          {loading ? 'Creating...' : 'Create User'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default CreateUser;
