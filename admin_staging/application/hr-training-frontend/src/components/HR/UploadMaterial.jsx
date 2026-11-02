import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  Typography,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
} from '@mui/material';
import { CloudUpload } from '@mui/icons-material';
import { materialService } from '../../services/auth';

const UploadMaterial = ({ open, onClose, onUploadSuccess }) => {
  const [formData, setFormData] = useState({
    group_name: '',
    training_type: 'New Hire',
  });
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);

  const handleFileChange = (event) => {
    setFiles(Array.from(event.target.files));
  };

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleUpload = async () => {
    if (!formData.group_name || files.length === 0) {
      alert('Please fill all fields and select files');
      return;
    }

    setUploading(true);
    
    try {
      // Create FormData for file upload
      const uploadFormData = new FormData();
      
      // Append each file
      files.forEach((file) => {
        uploadFormData.append('files', file);
      });

      // Call service with separate parameters
      await materialService.uploadMaterial(
        formData.group_name,      // String
        formData.training_type,   // String
        uploadFormData            // FormData object with files
      );

      alert('Upload successful!');
      onUploadSuccess();
      onClose();
      
      // Reset form
      setFormData({ group_name: '', training_type: 'New Hire' });
      setFiles([]);
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Upload failed: ' + (error.response?.data?.message || error.response?.data?.detail || error.message));
    } finally {
      setUploading(false);
    }
  };

  const handleClose = () => {
    setFormData({ group_name: '', training_type: 'New Hire' });
    setFiles([]);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Upload Training Materials</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, pt: 2 }}>
          <TextField
            label="Group Name"
            name="group_name"
            value={formData.group_name}
            onChange={handleChange}
            fullWidth
            required
          />

          <FormControl fullWidth required>
            <InputLabel>Training Type</InputLabel>
            <Select
              name="training_type"
              value={formData.training_type}
              onChange={handleChange}
              label="Training Type"
            >
              <MenuItem value="New Hire">New Hire</MenuItem>
              <MenuItem value="Existing Employee">Existing Employee</MenuItem>
            </Select>
          </FormControl>

          <Button
            variant="outlined"
            component="label"
            startIcon={<CloudUpload />}
            fullWidth
            sx={{ py: 2, borderStyle: 'dashed' }}
          >
            Select Files
            <input
              type="file"
              hidden
              multiple
              onChange={handleFileChange}
              accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx"
            />
          </Button>

          {files.length > 0 && (
            <Box>
              <Typography variant="body2" color="text.secondary">
                {files.length} file(s) selected:
              </Typography>
              {files.map((file, index) => (
                <Typography key={index} variant="body2">
                  • {file.name}
                </Typography>
              ))}
            </Box>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={uploading}>
          Cancel
        </Button>
        <Button
          onClick={handleUpload}
          variant="contained"
          disabled={uploading}
        >
          {uploading ? 'Uploading...' : 'Upload'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default UploadMaterial;
