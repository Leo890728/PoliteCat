from datetime import datetime
from typing import Optional, Union

import discord

from sqlmodel import Field, SQLModel, Relationship


class Drawbox(SQLModel, table=True):
    __tablename__ = "Drawbox"

    guild_id: int = Field(primary_key=True, sa_column_kwargs={"name": "GuildId"})
    box_name: str = Field(primary_key=True, sa_column_kwargs={"name": "BoxName"})
    creator_id: int = Field(sa_column_kwargs={"name": "CreatorId"})
    is_private: bool = Field(default=True, sa_column_kwargs={"name": "IsPrivate"})


class DrawboxItem(SQLModel, table=True):
    __tablename__ = "DrawboxItem"

    guild_id: int = Field(foreign_key="Drawbox.GuildId", sa_column_kwargs={"name": "GuildId"})
    box_name: str = Field(foreign_key="Drawbox.BoxName", sa_column_kwargs={"name": "BoxName"})
    value: str = Field(primary_key=True, sa_column_kwargs={"name": "Value"})


def setup(bot):
    pass

# /******************************************************************************

#                             Online Java Compiler.
#                 Code, Compile, Run and Debug java program online.
# Write your code in this editor and press "Run" button to execute it.

# *******************************************************************************/
# import java.util.Scanner;

# public class Main
# {
# 	public static void main(String[] args) {
# 	    System.out.println("請輸入兩個數字\n");

# 		double num1 = input("請輸入第一個數字：", "請重新輸入");
		
# 		double num2 = input("請輸入第二個數字：", "請重新輸入");
		
# 		double sum = num1 + num2;
# 		System.out.println(String.format("\n%s + %s = %s", num1, num2, sum));
# 	}
	
# 	public static double input(String prompt, String errorPrompt, Int) {
# 	    try {
# 	        System.out.println(prompt);
# 	        Scanner scanner = new Scanner(System.in);
# 	        return scanner.nextDouble();
# 	    } 
# 	    catch (java.util.InputMismatchException ex) {
# 	        System.out.println(errorPrompt);
# 	        return input(prompt, errorPrompt);
# 	    }
# 	}
# }