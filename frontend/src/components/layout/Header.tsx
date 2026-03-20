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
    <header className="bg-sidebar border-b border-border sticky top-0 z-50">
      <div className="flex items-center justify-between h-16 px-4 sm:px-6">
        {/* Left section */}
        <div className="flex items-center gap-3 flex-1">
          {onMenuClick && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onMenuClick}
              className="lg:hidden text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-white/10"
            >
              <Menu className="w-5 h-5" />
            </Button>
          )}

          {/* Logo */}
          <div 
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 cursor-pointer"
          >
            <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center">
              <span className="text-brand-foreground font-bold text-lg">D</span>
            </div>
            <span className="text-sidebar-foreground font-semibold text-lg hidden sm:block">
              Dopamine AI
            </span>
          </div>
        </div>

        {/* Center - Search (hidden on mobile) */}
        <div className="hidden md:block flex-1 max-w-md">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search videos..."
              className="w-full pl-9 bg-background/10 border-border text-sidebar-foreground placeholder:text-muted-foreground focus:border-brand focus:ring-brand/20"
            />
          </div>
        </div>

        {/* Right section */}
        <div className="flex items-center gap-2 flex-1 justify-end">
          {/* Mobile search icon */}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-white/10"
          >
            <Search className="w-5 h-5" />
          </Button>

          {/* Notifications */}
          <Button
            variant="ghost"
            size="icon"
            className="relative text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-white/10"
          >
            <Bell className="w-5 h-5" />
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-destructive rounded-full ring-2 ring-sidebar" />
          </Button>

          {/* User menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="flex items-center gap-2 text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-white/10"
              >
                <div className="w-8 h-8 rounded-full bg-brand flex items-center justify-center">
                  <User className="w-4 h-4 text-brand-foreground" />
                </div>
                <span className="hidden sm:block text-sm text-sidebar-foreground">John Doe</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 bg-card border-border">
              <DropdownMenuLabel className="text-foreground">My Account</DropdownMenuLabel>
              <DropdownMenuSeparator className="bg-border" />
              <DropdownMenuItem 
                onClick={() => navigate('/profile')}
                className="text-foreground hover:bg-accent focus:bg-accent cursor-pointer"
              >
                Profile
              </DropdownMenuItem>
              <DropdownMenuItem 
                onClick={() => navigate('/settings')}
                className="text-foreground hover:bg-accent focus:bg-accent cursor-pointer"
              >
                Settings
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-border" />
              <DropdownMenuItem className="text-destructive hover:bg-destructive/10 focus:bg-destructive/10 cursor-pointer">
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Mobile search bar (hidden by default, can be toggled) */}
      <div className="md:hidden px-4 pb-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search videos..."
            className="w-full pl-9 bg-background/10 border-border text-sidebar-foreground placeholder:text-muted-foreground"
          />
        </div>
      </div>
    </header>
  );
};