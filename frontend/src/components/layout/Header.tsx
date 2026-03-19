// src/components/layout/Header.tsx
import React from 'react';
import { Bell, Menu, Search, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface HeaderProps {
  onMenuClick?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onMenuClick }) => {
  const navigate = useNavigate();

  return (
    <header className="bg-dopamine-dark border-b border-gray-800 sticky top-0 z-50">
      <div className="flex items-center justify-between h-16 px-4 sm:px-6">
        {/* Left section */}
        <div className="flex items-center gap-3 flex-1">
          {onMenuClick && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onMenuClick}
              className="lg:hidden text-gray-300 hover:text-white hover:bg-dopamine-accent/20"
            >
              <Menu className="w-5 h-5" />
            </Button>
          )}

          {/* Logo */}
          <div 
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 cursor-pointer"
          >
            <div className="w-8 h-8 rounded-lg bg-dopamine-accent flex items-center justify-center">
              <span className="text-white font-bold text-lg">D</span>
            </div>
            <span className="text-white font-semibold text-lg hidden sm:block">
              Dopamine AI
            </span>
          </div>
        </div>

        {/* Center - Search (hidden on mobile) */}
        <div className="hidden md:block flex-1 max-w-md">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Search videos..."
              className="w-full pl-9 bg-dopamine-dark/50 border-gray-700 text-white placeholder:text-gray-400 focus:border-dopamine-accent"
            />
          </div>
        </div>

        {/* Right section */}
        <div className="flex items-center gap-2 flex-1 justify-end">
          {/* Mobile search icon */}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden text-gray-300 hover:text-white hover:bg-dopamine-accent/20"
          >
            <Search className="w-5 h-5" />
          </Button>

          {/* Notifications */}
          <Button
            variant="ghost"
            size="icon"
            className="relative text-gray-300 hover:text-white hover:bg-dopamine-accent/20"
          >
            <Bell className="w-5 h-5" />
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-500 rounded-full ring-2 ring-dopamine-dark" />
          </Button>

          {/* User menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="flex items-center gap-2 text-gray-300 hover:text-white hover:bg-dopamine-accent/20"
              >
                <div className="w-8 h-8 rounded-full bg-dopamine-accent flex items-center justify-center">
                  <User className="w-4 h-4 text-white" />
                </div>
                <span className="hidden sm:block text-sm">John Doe</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>My Account</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => navigate('/profile')}>
                Profile
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/settings')}>
                Settings
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-red-600">
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Mobile search bar (hidden by default, can be toggled) */}
      <div className="md:hidden px-4 pb-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            placeholder="Search videos..."
            className="w-full pl-9 bg-dopamine-dark/50 border-gray-700 text-white placeholder:text-gray-400"
          />
        </div>
      </div>
    </header>
  );
};