// src/components/layout/PageHeader.tsx
import React from 'react';
import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface PageHeaderProps {
  title?: string;
  viewMode?: 'admin' | 'student';
  setViewMode?: (mode: 'admin' | 'student') => void;
  backLink?: string;
  actions?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  viewMode = 'student',
  setViewMode,
  backLink,
  actions,
}) => {
  const navigate = useNavigate();

  const handleBack = () => {
    if (backLink) {
      navigate(backLink);
    } else {
      navigate(-1);
    }
  };

  return (
    <div className="bg-white border-b border-gray-200 sticky top-16 z-40">
      <div className="max-w-7xl mx-auto px-4 py-4">
        {/* Top row with back button and actions */}
        <div className="flex items-center justify-between mb-2">
          <Button
            variant="ghost"
            onClick={handleBack}
            className="gap-2 text-gray-600 hover:text-dopamine-accent hover:bg-dopamine-light"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </Button>
          
          {actions && (
            <div className="flex items-center gap-2">
              {actions}
            </div>
          )}
        </div>

        {/* Bottom row with title and view mode toggle */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          {title && (
            <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          )}

          {setViewMode && (
            <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'admin' | 'student')}>
              <TabsList className="bg-gray-100">
                <TabsTrigger 
                  value="student" 
                  className="data-[state=active]:bg-dopamine-accent data-[state=active]:text-white"
                >
                  Student View
                </TabsTrigger>
                <TabsTrigger 
                  value="admin"
                  className="data-[state=active]:bg-dopamine-accent data-[state=active]:text-white"
                >
                  Admin View
                </TabsTrigger>
              </TabsList>
            </Tabs>
          )}
        </div>
      </div>
    </div>
  );
};