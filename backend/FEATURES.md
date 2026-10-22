# Exam Paper Management Features

## Overview
This document describes the new features added to the Django backend for managing exam papers, specifically the ability to delete exam papers and update their year information.

## New Features

### 1. Delete Exam Papers
**Purpose**: Allows users to permanently delete exam papers they have uploaded.

**How to use**:
1. Navigate to any exam paper detail page (`/exams/<id>/`)
2. Click the red "Delete" button in the Actions section
3. Review the confirmation page showing what will be deleted
4. Click "Delete Exam Paper" to confirm

**What gets deleted**:
- The exam paper record from the database
- Associated topics and analysis data
- All predictions based on this exam paper
- The uploaded file from the server storage

**Security**: Only the user who uploaded the exam paper can delete it.

### 2. Update Exam Year
**Purpose**: Allows users to change the year associated with an exam paper. This is useful when administrators upload PDFs containing questions from multiple years.

**How to use**:
1. Navigate to any exam paper detail page (`/exams/<id>/`)
2. Click the yellow "Change Year" button in the Actions section
3. Enter the correct year (1900-2100)
4. Click "Update Year" to save

**Validation**:
- Year must be between 1900 and 2100
- Cannot create duplicate exam papers (same user, title, and year)
- Proper error messages for validation failures

**Security**: Only the user who uploaded the exam paper can update it.

## Technical Implementation

### URLs Added
- `/exams/<int:pk>/delete/` - Delete confirmation and action
- `/exams/<int:pk>/update-year/` - Year update form and action

### Templates Added
- `confirm_delete.html` - Confirmation page for deletion
- `update_year.html` - Form for updating exam year

### Forms Added
- `ExamDeleteForm` - Confirmation checkbox for deletion
- `ExamYearUpdateForm` - Year input with validation

### Database Changes
- Added year field validation (MinValueValidator, MaxValueValidator)
- Enhanced unique constraint handling

### Error Handling
- Comprehensive validation for year updates
- File cleanup on deletion
- User authorization checks
- Proper success/error messages

## Testing Results
Based on server logs, the delete functionality has been successfully tested:
- Delete confirmation page loads correctly
- Delete action executes and redirects properly
- File cleanup and database integrity maintained

## Usage Notes
- All actions require user authentication
- Changes are irreversible (especially deletion)
- Year updates respect database constraints
- Success messages confirm completed actions